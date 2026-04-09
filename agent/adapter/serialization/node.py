from typing import Any, Dict

from agent.domain.context import Node


def node_to_dict(node: Node) -> Dict[str, Any]:
    """Serialize a Node (and its children) into a plain dict.

    This avoids following the parent pointer to prevent cycles
    and converts enums/datetimes into JSON-friendly values.
    """

    return {
        "id": str(node.id),
        "value": node.value,
        "type": node.type.name,
        "status": node.status.name,
        "tool_name": node.tool_name,
        "tool_args": node.tool_args,
        "tool_response": node.tool_response,
        "tool_response_summary": node.tool_response_summary,
        "preconditions": list(node.preconditions) if node.preconditions is not None else [],
        "effects": list(node.effects) if node.effects is not None else [],
        "next": node.next,
        "previous": node.previous,
        "created_at": node.created_at.isoformat() if hasattr(node.created_at, "isoformat") else None,
        "children": [node_to_dict(child) for child in (node.children or [])],
        "parent_id": str(node.parent.id) if node.parent is not None else None
        # no "parent" to avoid cycles
    }