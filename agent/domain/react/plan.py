from agent.domain.agent import Agent
from agent.domain.context import Context, NodeType, NodeStatus
from agent.application.usecases.prompt_rendering import render_prompt
from agent.domain.prompts.react.parameter_generation import parameter_generation_prompt

from agent.logger import get_logger

import json


logger = get_logger(__name__)

def _mark_subtree_cached(node):
    stack = [node]
    while stack:
        current = stack.pop()
        current.cached = True
        stack.extend(current.children or [])


async def plan_parameters(agent_session: Agent):

    # build parameter generation prompt
    previous_nodes_list = agent_session.context.previous_nodes(agent_session.active_node)
    next_nodes_list = agent_session.context.next_nodes(agent_session.active_node)

    previous_nodes = agent_session.context.represent_nodes(nodes=previous_nodes_list)
    next_nodes = agent_session.context.represent_nodes(nodes=next_nodes_list)
    current_node = agent_session.context.represent_nodes(nodes=[agent_session.active_node])

    tool_spec = agent_session.tools.get_tool_spec(agent_session.active_node.tool_name)

    parameter_generation_prompt_rendered = render_prompt(
        agent_session=agent_session,
        template=parameter_generation_prompt,
        context={
            "global_goal": agent_session.global_goal_node.value,
            "current_node": current_node,
            "tool_spec": tool_spec,
            "history": previous_nodes,
            "future_nodes": next_nodes,
        },
    )

    llm_result = agent_session.llm.call(
        prompt=parameter_generation_prompt_rendered,
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


# create a new plan
async def plan(agent_session: Agent):

    if not agent_session.active_node:
        return

    # TODO: put this into own function
    # case: agent plan didn't worked and needs a new plan for prgressing
    if agent_session.active_node.node_type == NodeType.abstract and agent_session.active_node.children:
        tool_docs = await agent_session.tools.get_tools_json()

        extension_root, llm_result = agent_session.planner.extend_plan(
            context=agent_session.context,
            root=agent_session.active_node,
            tool_docs=tool_docs,
            run_id=agent_session.run_id,
        )

        agent_session.record_llm_usage(
            phase="extend_plan",
            llm_result=llm_result,
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
        memory_type="procedural",
    )

    # Fallback: some persisted procedural roots are fully_planned.
    # If abstract-only retrieval misses, retry without type restriction.
    if existing_plan is None:
        fallback_filter = {
            "collection": "nodes_value",
            "n_results": 10,
            "max_distance": 1,
            "root_only": True,
            "prefer_abstract": False,
        }
        existing_plan = agent_session.memory.query(
            agent_session.active_node.value,
            filter=fallback_filter,
            memory_type="procedural",
        )

    # if plan exists wire it into the context tree
    if existing_plan:
        replacement_root = existing_plan.get_root()
        if not replacement_root:
            raise RuntimeError("Procedural memory returned a context without a root")

        # wireing here
        inserted_root = agent_session.context.replace_node_with_subtree(
            target_node=agent_session.active_node,
            replacement_root=replacement_root,
        )

        if inserted_root is None:
            raise RuntimeError("replace_node_with_subtree() must return the inserted root")

        _mark_subtree_cached(inserted_root)
        agent_session.skip_reflection = True
        agent_session.context.rebuild_indexes()

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

        # TODO: remove later
        serialized_context = agent_session.planner.serializer.serialize_context(agent_session.context)
        logger.info("%s:\n%s", "Context Tree", json.dumps(serialized_context, indent=2, default=str))

    # no existing path available so we expand the node
    else:
        tool_docs = await agent_session.tools.get_tools_json()

        # generate plan
        agent_session.context, llm_result = agent_session.planner.plan(
            context=agent_session.context,
            root=agent_session.active_node,
            tool_docs=tool_docs,
            run_id=agent_session.run_id,
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
async def replan(agent_session: Agent):
    

    # get failed node, tool specs
    failed_node = agent_session.active_node
    tool_docs = await agent_session.tools.get_tools_json()

    # send request to llm
    agent_session.context, llm_result = agent_session.planner.replan(
        context=agent_session.context,
        root=failed_node,
        tool_docs=tool_docs,
        run_id=agent_session.run_id,
    )

    # update active node to new replanned node
    # write usage to analytics db
    agent_session.record_llm_usage(
        phase="replan",
        llm_result=llm_result,
    )

    # re-binding the agent to the current root
    agent_session.global_goal_node = agent_session.context.get_root()
    if not agent_session.global_goal_node:
        raise RuntimeError("No root available after replanning")

    agent_session.active_node = agent_session.context.next_node(failed_node) or agent_session.context.select_frontier_node(agent_session.global_goal_node) or agent_session.global_goal_node




