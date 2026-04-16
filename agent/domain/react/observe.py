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

    # build context for tool response summary
    global_goal = str(agent_session.global_goal_node)
    previous_nodes_list = agent_session.context.previous_nodes(agent_session.active_node)
    next_nodes_list = agent_session.context.next_nodes(agent_session.active_node)

    previous_nodes = agent_session.context.represent_nodes(nodes=previous_nodes_list)
    next_nodes = agent_session.context.represent_nodes(nodes=next_nodes_list)
    current_node = agent_session.context.represent_nodes(nodes=[agent_session.active_node])

    # format
    step_observation_prompt_rendered = render_prompt(
        agent_session=agent_session,
        template=step_observation_prompt,
        context={
            "global_goal": global_goal,
            "previous_nodes": previous_nodes,
            "next_nodes": next_nodes,
            "current_node": current_node,
        },
    )

    try:
        response = json.loads(agent_session.llm.call(prompt=step_observation_prompt_rendered))

        agent_session.active_node.tool_response_summary = response.get("summary")

        parameter_updates = response.get("parameter_updates")
        if isinstance(parameter_updates, list) and parameter_updates:
            agent_session.context.update_parameters(parameter_updates=parameter_updates)

        

        if response.get("has_error"):
            agent_session.active_node.status = NodeStatus.failed
        else:
            agent_session.active_node.status = NodeStatus.success


         # bubble up completion to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)

        metadata = agent_session.memory.save(context=agent_session.context)
        logger.debug("Persisted context metadata: %s", metadata)
        logger.info(
            "Observation summary node=%s: %s",
            agent_session.active_node.id,
            agent_session.active_node.tool_response_summary,
        )


        # stay at failed node for replanning
        if agent_session.active_node.status == NodeStatus.failed:
            return
        
        # set next active node if a next node exists
        if (next_node := agent_session.context.next_node(agent_session.active_node)):
            agent_session.active_node = next_node

    except Exception as e:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)

        raise RuntimeError(f"Observation has failed: {e}") from e