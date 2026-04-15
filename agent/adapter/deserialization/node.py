from typing import Any, Mapping

from agent.domain.context import Node, NodeType, NodeStatus
import json
from datetime import datetime


# deserialization: dict / JSON -> Node tree
def node_from_dict(data: Mapping[str, Any]) -> Node:
    """Build a Node (and its children) from a plain dict.

    The function is defensive about missing/invalid fields and
    never trusts incoming parent references to avoid cycles.
    """

    if not isinstance(data, dict):
        raise TypeError("node_from_dict expects a dict-like object")

    # Start with only fields that exist on the Node dataclass.
    known_fields = set(Node.__dataclass_fields__.keys())  # type: ignore[attr-defined]
    kwargs: dict[str, Any] = {k: v for k, v in data.items() if k in known_fields}

    # Never take parent/children from the wire format directly.
    kwargs.pop("parent", None)
    children_data = data.get("children") or []
    kwargs.pop("children", None)

    # Enums: tolerate missing/unknown values by falling back to defaults.
    raw_type = data.get("type")
    if isinstance(raw_type, str) and raw_type in NodeType.__members__:
        kwargs["node_type"] = NodeType[raw_type]

    raw_status = data.get("status")
    if isinstance(raw_status, str) and raw_status in NodeStatus.__members__:
        kwargs["node_status"] = NodeStatus[raw_status]

    # Datetime: parse ISO string if present and valid.
    # If explicitly null/None, drop the field so Node's default_factory runs.
    raw_created = data.get("created_at")
    if isinstance(raw_created, str):
        try:
            kwargs["created_at"] = datetime.fromisoformat(raw_created)
        except ValueError:
            # fall back to default by not setting created_at
            kwargs.pop("created_at", None)
    elif raw_created is None and "created_at" in kwargs:
        # Let the dataclass default_factory(datetime.now) supply a value
        kwargs.pop("created_at", None)

    # Ensure we at least pass a value field; allow None if absent, as before.
    if "value" not in kwargs:
        kwargs["value"] = data.get("value")

    node = Node(**kwargs)

    # Children must be a list of dicts; ignore anything malformed.
    if not isinstance(children_data, list):
        children_data = []

    for child_dict in children_data:
        if not isinstance(child_dict, dict):
            continue
        child = node_from_dict(child_dict)
        child.parent = node
        node.children.append(child)

    return node


def from_json(s: str) -> Node:
    """Deserialize a JSON string into a Node tree.

    Handles both plain node objects and planner-style wrappers
    of the form {"root": {...}}.
    """

    loaded = json.loads(s)
    if isinstance(loaded, dict) and "root" in loaded:
        return node_from_dict(loaded["root"])
    return node_from_dict(loaded)