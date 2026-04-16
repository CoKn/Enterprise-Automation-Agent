from agent.domain.agent import Agent
from agent.domain.context import NodeType, NodeStatus
from agent.logger import get_logger


logger = get_logger(__name__)

async def act(agent_session: Agent):
    # If planning did not set an active node, there is nothing to do.
    if not agent_session.active_node:
        return
    
    # if the current node is abstract do not try to execute
    if agent_session.active_node.node_type == NodeType.abstract:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)

        raise RuntimeError(
            f"Cannot execute node '{agent_session.active_node.id}' before it is fully planned"
        )
    
    # if the current node is parcially planned do not try to execute
    if agent_session.active_node.node_type == NodeType.parcially_planned:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)

        raise RuntimeError(
            f"Cannot execute node '{agent_session.active_node.id}' before it is fully planned"
        )
    

    # case fully planned:
    tool_name = agent_session.active_node.tool_name
    if not tool_name:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)
        raise ValueError(f"Missing 'tool_name' in active node: {agent_session.active_node}")
    
    tool_args = agent_session.active_node.tool_args or {}

    logger.debug(
        "Executing tool %s with args=%s on node=%s",
        tool_name,
        tool_args,
        agent_session.active_node.id,
    )

    try:
        agent_session.active_node.tool_response = await agent_session.tools.execute_tool(
            fn_name=tool_name,
            fn_args=tool_args,
        )
        logger.debug(
            "Tool response for %s on node=%s: %s",
            tool_name,
            agent_session.active_node.id,
            agent_session.active_node.tool_response,
        )

        return
    
    except Exception as e:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)

        raise RuntimeError(f"Tool execution failed for '{tool_name}': {e}") from e