from typing import Any

import json

from agent.domain.context import Context, Node
from agent.adapter.serialization.node import node_to_dict


def context_to_dict(context: Context) -> Any:
	"""Serialize Context roots into plain Python data.

	- Single root: returns one dict for backwards compatibility.
	- Multiple roots: returns a list of root dicts.
	- No roots: returns None.
	"""

	roots = context.roots

	if not roots:
		return None

	if len(roots) == 1:
		return node_to_dict(roots[0])

	return [node_to_dict(n) for n in roots]


def to_json(context: Context, **json_kwargs: Any) -> str:
	"""Serialize a Context to a JSON string.

	Any additional keyword arguments are passed through to json.dumps.
	"""

	plain = context_to_dict(context)
	return json.dumps(plain, **json_kwargs)


from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4


def add_uuid(context: Dict[str, Any]) -> None:
    root = context.get("root", context)

    def assign(node: Dict[str, Any]) -> None:
        if not node.get("id"):
            node["id"] = str(uuid4())
        for child in node.get("children") or []:
            assign(child)

    assign(root)


def add_next_previous_references(context: Dict[str, Any]) -> None:
    # root references first leaf node
    root = context.get("root", context)

    leaves: List[Dict[str, Any]] = []

    def collect_leaves(node: Dict[str, Any]) -> None:
        children = node.get("children") or []
        if not children:
            leaves.append(node)
            return
        for child in children:
            collect_leaves(child)

    collect_leaves(root)

    if leaves:
        # root points to the first actionable leaf; root has no previous.
        root["next"] = leaves[0].get("id")
        root["previous"] = None

    # Wire up the next and previous references between leaves.
    for idx, node in enumerate(leaves):
        # previous: link to the prior leaf in the linear order (or None for the first)
        if idx == 0:
            node["previous"] = None
        else:
            prev_node = leaves[idx - 1]
            node["previous"] = prev_node.get("id")

        # next: link to the next leaf in the linear order (or None for the last)
        if idx + 1 < len(leaves):
            next_node = leaves[idx + 1]
            node["next"] = next_node.get("id")
        else:
            node["next"] = None




def flatten_nodes(serialized_context: Any) -> List[Dict[str, Any]]:

    nodes: List[Dict[str, Any]] = []

    def collect(node_dict: Dict[str, Any]) -> None:
        nodes.append(node_dict)
        for child in node_dict.get("children") or []:
            collect(child)

    if isinstance(serialized_context, dict):
        collect(serialized_context)
    elif isinstance(serialized_context, list):
        for root in serialized_context:
            collect(root)

    return nodes


def check_if_folder_exists(path: str) -> Path:
    folder_path = Path(path).expanduser()
    if not folder_path.exists():
        folder_path.mkdir(parents=True, exist_ok=True)

    return folder_path