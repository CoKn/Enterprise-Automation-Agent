from typing import Any

import json

from agent.domain.context import Context, Node
from agent.adapter.serialization.node import node_to_dict


def context_to_dict(context: Context) -> Any:
	"""Serialize a Context's data_structure into plain Python data.

	- If the context holds a single Node, returns a dict.
	- If it holds a list of Nodes, returns a list of dicts.
	- If it is empty, returns None.
	"""

	data = context.data_structure

	if data is None:
		return None

	if isinstance(data, Node):
		return node_to_dict(data)

	if isinstance(data, list):
		return [node_to_dict(n) for n in data]

	# Fallback: return as-is if it's some other type.
	return data


def to_json(context: Context, **json_kwargs: Any) -> str:
	"""Serialize a Context to a JSON string.

	Any additional keyword arguments are passed through to json.dumps.
	"""

	plain = context_to_dict(context)
	return json.dumps(plain, **json_kwargs)

