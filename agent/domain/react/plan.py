from agent.domain.agent import Agent
from agent.domain.context import Context, NodeType, NodeStatus
from agent.domain.prompt_rendering import (build_parameter_generation_prompt,
                                           build_plan_extention_prompt,
                                           build_replanning_prompt,
                                           build_planning_prompt
                                           )

from agent.logger import get_logger

import json


logger = get_logger(__name__)


# generate parameters for parcially planned node
async def plan_parameters(agent_session: Agent):

    llm_result = agent_session.llm.call(
        prompt=build_parameter_generation_prompt(agent_session=agent_session),
        json_mode=True,
    )

    if llm_result.get("error"):
        raise RuntimeError(llm_result["error"])

    logger.info(
        "LLM usage phase=parameter_generation prompt_tokens=%s completion_tokens=%s total_tokens=%s",
        llm_result.get("prompt_tokens", 0),
        llm_result.get("completion_tokens", 0),
        llm_result.get("total_tokens", 0),
    )

    agent_session.record_llm_usage(
        phase="parameter_generation",
        llm_result=llm_result,
    )

    resp = llm_result.get("response") or ""

    try:
        parsed = json.loads(resp)
        arguments = parsed.get("arguments")

        if not isinstance(arguments, dict):
            raise ValueError("Parameter generation must return a JSON object with an 'arguments' dict")

        agent_session.active_node.tool_args = arguments
        agent_session.active_node.node_type = NodeType.fully_planned
        agent_session.active_node.node_status = NodeStatus.pending

        logger.info(
            "Parameter generation completed for node='%s'",
            agent_session.active_node.value,
        )
        return

    except (json.JSONDecodeError, ValueError) as e:
        agent_session.active_node.node_status = NodeStatus.failed
        agent_session.context.recompute_statuses()
        agent_session.memory.save(context=agent_session.context)

        raise ValueError(
            "Parameter generation response must be valid JSON with an 'arguments' object"
        ) from e
    

# generate an entire new plan
async def replan(agent_session: Agent):

    if not agent_session.active_node:
        return

    # build prompt and generate new plan
    prompt = build_plan_extention_prompt(agent_session=agent_session),
    extension_root, llm_result = agent_session.planner.extend_plan(
        prompt=prompt
    )

    agent_session.record_llm_usage(
        phase="extend_plan",
        llm_result=llm_result
    )

    agent_session.context.extend_node_with_subtree(
        target_node=agent_session.active_node,
        extension_root=extension_root,
    )

    agent_session.global_goal_node = agent_session.context.get_root()
    if not agent_session.global_goal_node:
        raise RuntimeError("No root available after plan extension")

    agent_session.active_node = agent_session.context.select_frontier_node(agent_session.global_goal_node)
    return


# create a new plan
async def plan(agent_session: Agent):

    # active node is abstract and needs expantion
    if not agent_session.active_node:
        return


    # if node type is abstract check if active node is already in procedural memory
    filter_ = {
        "collection": "nodes_value",
        "n_results": 10,
        "max_distance": 0.5,
        "root_only": True,
        "prefer_abstract": True,
    }
    existing_plan: Context | None = agent_session.memory.query(
        agent_session.active_node.value,
        filter=filter_,
        memory_type="procedural"
    )


    # if plan exists wire it into the context tree
    if existing_plan:
        replacement_root = existing_plan.get_root()
        if not replacement_root:
            raise RuntimeError("Procedural memory returned a context without a root")

        inserted_root = agent_session.context.insert_cached_subtree(
            target_node=agent_session.active_node,
            replacement_root=replacement_root
        )

        if inserted_root is None:
            raise RuntimeError("insert_cached_subtree() must return the inserted root")

        agent_session.global_goal_node = agent_session.context.get_root()
        if not agent_session.global_goal_node:
            raise RuntimeError("No root available after cached plan insertion")

        # re-binding the agent to the current root
        agent_session.active_node = (
            agent_session.context.select_frontier_node(inserted_root)
            or agent_session.context.select_frontier_node(agent_session.global_goal_node)
            or inserted_root
        )

        logger.info(
            "Reusing cached plan for node '%s' type=%s cached=%s",
            inserted_root.value,
            inserted_root.node_type.name,
            inserted_root.cached,
        )

    # no existing path available so we create a new plan
    else:

        prompt = build_planning_prompt(agent_session=agent_session)

        # generate plan
        agent_session.context, llm_result = agent_session.planner.plan(
            prompt=prompt
        )

        # write usage to analytics db
        agent_session.record_llm_usage(
            phase="plan",
            llm_result=llm_result,
        )

        # re-binding the agent to the current root
        agent_session.global_goal_node = agent_session.context.get_root()
        if not agent_session.global_goal_node:
            raise RuntimeError("No root available after planning")

        agent_session.active_node = agent_session.context.select_frontier_node(agent_session.global_goal_node) or agent_session.global_goal_node

        if agent_session.active_node:
            logger.info(
                "Planner produced frontier node goal='%s' type=%s status=%s",
                agent_session.active_node.value,
                agent_session.active_node.node_type.name,
                agent_session.active_node.node_status.name,
            )

    return


# repair a plan
async def repair(agent_session: Agent):
    

    # get failed node, tool specs
    failed_node = agent_session.active_node

    # send request to llm
    prompt = build_replanning_prompt(agent_session=agent_session)
    agent_session.context, llm_result = agent_session.planner.replan(
        prompt=prompt,
        context=agent_session.context,
        failed_node=failed_node,
    )

    # write usage to analytics db
    agent_session.record_llm_usage(
        phase="replan",
        llm_result=llm_result
    )

    # re-binding the agent to the current root
    agent_session.global_goal_node = agent_session.context.get_root()
    if not agent_session.global_goal_node:
        raise RuntimeError("No root available after replanning")

    agent_session.active_node = (
        agent_session.context.next_node(failed_node)
        ) or (
        agent_session.context.select_frontier_node(agent_session.global_goal_node)
        ) or (
        agent_session.global_goal_node
    )



