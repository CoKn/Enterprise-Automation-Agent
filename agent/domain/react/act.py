from agent.domain.agent import Agent
from agent.domain.context import NodeType, NodeStatus
from agent.logger import get_logger


logger = get_logger(__name__)


async def act(agent_session: Agent):
    if not agent_session.active_node:
        return

    node = agent_session.active_node

    # These are scheduler/control-flow errors, not execution failures.
    if node.node_type == NodeType.abstract:
        raise RuntimeError(
            f"Programming error: act() called on abstract node '{node.id}'"
        )

    if node.node_type == NodeType.parcially_planned:
        raise RuntimeError(
            f"Programming error: act() called on parcially_planned node '{node.id}'"
        )

    if node.node_type != NodeType.fully_planned:
        raise RuntimeError(
            f"Programming error: act() called on unsupported node type '{node.node_type}'"
        )

    tool_name = node.tool_name
    if not tool_name:
        node.node_status = NodeStatus.failed
        agent_session.context.recompute_statuses()
        agent_session.memory.save(context=agent_session.context)
        raise ValueError(f"Missing 'tool_name' in active node: {node}")

    tool_args = node.tool_args or {}

    logger.debug(
        "Executing tool %s with args=%s on node=%s",
        tool_name,
        tool_args,
        node.id,
    )

    try:
        node.tool_response = await agent_session.tools.execute_tool(
            fn_name=tool_name,
            fn_args=tool_args,
        )

        tool_response = node.tool_response
        if isinstance(tool_response, dict) and bool(tool_response.get("is_error")):
            node.node_status = NodeStatus.failed

        logger.debug(
            "Tool response for %s on node=%s: %s",
            tool_name,
            node.id,
            node.tool_response,
        )

        return

    except Exception as e:
        node.node_status = NodeStatus.failed
        agent_session.context.recompute_statuses()
        agent_session.memory.save(context=agent_session.context)

        raise RuntimeError(f"Tool execution failed for '{tool_name}': {e}") from e