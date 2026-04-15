from datetime import date, datetime
from enum import Enum
from typing import Any, Dict
from uuid import UUID

from agent.domain.context import Node


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (UUID,)):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Enum):
        return value.name

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))

    if hasattr(value, "dict"):
        try:
            return _json_safe(value.dict())
        except Exception:
            pass

    return str(value)


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
        "tool_args": _json_safe(node.tool_args),
        "tool_response": _json_safe(node.tool_response),
        "tool_response_summary": node.tool_response_summary,
        "preconditions": list(node.preconditions) if node.preconditions is not None else [],
        "effects": list(node.effects) if node.effects is not None else [],
        "next": _json_safe(node.next),
        "previous": _json_safe(node.previous),
        "created_at": node.created_at.isoformat() if hasattr(node.created_at, "isoformat") else None,
        "children": [node_to_dict(child) for child in (node.children or [])],
        "parent_id": str(node.parent.id) if node.parent is not None else None
        # no "parent" to avoid cycles
    }