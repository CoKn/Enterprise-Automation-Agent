from agent.domain.agent import Agent
from agent.domain.context import NodeStatus
from agent.application.usecases.prompt_rendering import render_prompt
from agent.domain.prompts.react.step_observation import step_observation_prompt
from agent.logger import get_logger

import json


logger = get_logger(__name__)


async def observe(agent_session: Agent):
    if not agent_session.active_node:
        return

    # get active, previous and future nodes
    node = agent_session.active_node
    previous_nodes_list = agent_session.context.previous_nodes(node)
    next_nodes_list = agent_session.context.next_nodes(node)

    step_observation_prompt_rendered = render_prompt(
        agent_session=agent_session,
        template=step_observation_prompt,
        context={
            "global_goal": agent_session.global_goal_node.value,
            "previous_nodes": agent_session.context.represent_nodes(nodes=previous_nodes_list),
            "next_nodes": agent_session.context.represent_nodes(nodes=next_nodes_list),
            "current_node": agent_session.context.represent_nodes(nodes=[node]),
            "tracked_parameters": agent_session.context.get_leaf_nodes_tool_args(),
            "current_tool_response": node.tool_response,
        },
    )

    try:
        llm_result = agent_session.llm.call(
            json_mode=True,
            prompt=step_observation_prompt_rendered,
        )

        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        logger.info(
            "LLM usage phase=observe prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            llm_result.get("prompt_tokens", 0),
            llm_result.get("completion_tokens", 0),
            llm_result.get("total_tokens", 0),
        )

        agent_session.record_llm_usage(
            phase="observe",
            llm_result=llm_result,
        )

        response = json.loads(llm_result.get("response") or "{}")

        node.tool_response_summary = response.get("summary")

        parameter_updates = response.get("parameter_updates")
        if isinstance(parameter_updates, list) and parameter_updates:
            agent_session.context.update_parameters(parameter_updates=parameter_updates)

        if response.get("has_error"):
            node.node_status = NodeStatus.failed
        else:
            node.node_status = NodeStatus.completed

        # recompute parent statuses after the leaf update
        agent_session.context.recompute_statuses()

        metadata = agent_session.memory.save(context=agent_session.context)
        logger.debug("Persisted context metadata: %s", metadata)
        logger.info(
            "Observation summary node=%s: %s",
            node.id,
            node.tool_response_summary,
        )

        # keep failed node as active so the next cycle can replan/repair it
        if node.node_status == NodeStatus.failed:
            return

        # otherwise move to the next frontier node in the tree
        agent_session.active_node = agent_session.context.select_frontier_node(agent_session.global_goal_node)
        if agent_session.active_node is None:
            agent_session.termination = True

    except Exception as e:
        node.node_status = NodeStatus.failed
        agent_session.context.recompute_statuses()
        agent_session.memory.save(context=agent_session.context)
        agent_session.termination = True

        raise RuntimeError(f"Observation has failed: {e}") from e