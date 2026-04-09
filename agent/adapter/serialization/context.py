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

