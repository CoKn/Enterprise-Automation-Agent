from typing import Any

import json

from agent.domain.context import Context
from agent.adapter.deserialization.node import node_from_dict


def context_from_dict(data: Any) -> Context:
	"""Create a Context from plain Python data.

	Accepts:
	- a dict with an optional top-level "root" key;
	- a single node dict;
	- a list of node dicts.
	"""

	if isinstance(data, dict):
		# Planner-style wrapper: {"root": {...}}
		if "root" in data and isinstance(data["root"], dict):
			ds = [node_from_dict(data["root"])]
		else:
			ds = [node_from_dict(data)]
	elif isinstance(data, list):
		ds = [node_from_dict(d) for d in data if isinstance(d, dict)] if data else []
	else:
		ds = []

	return Context(roots=ds)


def from_json(s: str) -> Context:
	"""Deserialize a JSON string into a Context."""

	loaded = json.loads(s)
	return context_from_dict(loaded)

