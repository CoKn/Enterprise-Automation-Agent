from agent.domain.agent import Agent
from agent.domain.context import NodeStatus
from agent.domain.prompt_rendering import build_obervation_prompt
from agent.logger import get_logger

import json


logger = get_logger(__name__)


async def observe(agent_session: Agent):
    
    if not agent_session.active_node:
        return
    
    try:
        llm_result = agent_session.llm.call(
            json_mode=True,
            prompt=build_obervation_prompt(agent_session=Agent),
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

        agent_session.active_node.tool_response_summary = response.get("summary")

        parameter_updates = response.get("parameter_updates")
        if isinstance(parameter_updates, list) and parameter_updates:
            agent_session.context.update_parameters(parameter_updates=parameter_updates)

        if response.get("has_error"):
            agent_session.active_node.node_status = NodeStatus.failed
        else:
            agent_session.active_node.node_status = NodeStatus.completed

        # recompute parent statuses after the leaf update
        agent_session.context.recompute_statuses()

        metadata = agent_session.memory.save(context=agent_session.context)
        # logger.debug("Persisted context metadata: %s", metadata)
        logger.info(
            "Observation summary node=%s: %s",
            agent_session.active_node.id,
            agent_session.active_node.tool_response_summary,
        )

        # keep failed node as active so the next cycle can replan/repair it
        if agent_session.active_node.node_status == NodeStatus.failed:
            return

        # otherwise move to the next frontier node in the tree
        agent_session.active_node = agent_session.context.select_frontier_node(agent_session.global_goal_node)
        if agent_session.active_node is None:
            agent_session.termination = True

    except Exception as e:
        agent_session.active_node.node_status = NodeStatus.failed
        agent_session.context.recompute_statuses()
        agent_session.memory.save(context=agent_session.context)
        agent_session.termination = True

        raise RuntimeError(f"Observation has failed: {e}") from e