from dataclasses import is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from agent.application.ports.outbound.context_serializer_interface import ContextSerializer
from agent.domain.context import Context, Node, NodeStatus, NodeType


class ContextJsonSerializer(ContextSerializer):
    def _to_jsonable(self, value: Any):
        if value is None:
            return None
        if isinstance(value, Enum):
            return value.name
        if isinstance(value, (datetime, UUID)):
            return str(value)
        if isinstance(value, list):
            return [self._to_jsonable(v) for v in value]
        if isinstance(value, dict):
            return {k: self._to_jsonable(v) for k, v in value.items()}
        if is_dataclass(value):
            return {k: self._to_jsonable(v) for k, v in value.__dict__.items()}
        return value

    def serialize_node(self, node: Node) -> dict[str, Any]:
        return {
            "id": self._to_jsonable(node.id),
            "value": node.value,
            "node_status": self._to_jsonable(node.node_status),
            "node_type": self._to_jsonable(node.node_type),
            "created_at": self._to_jsonable(node.created_at),
            "preconditions": self._to_jsonable(node.preconditions),
            "effects": self._to_jsonable(node.effects),
            "tool_name": node.tool_name,
            "tool_args": self._to_jsonable(node.tool_args),
            "tool_response": self._to_jsonable(node.tool_response),
            "tool_response_summary": self._to_jsonable(node.tool_response_summary),
            "parent_id": self._to_jsonable(node.parent.id) if node.parent else None,
            "children_ids": [self._to_jsonable(child.id) for child in node.children],
            "next": self._to_jsonable(node.next),
            "previous": self._to_jsonable(node.previous),
        }

    def serialize_context(self, context: Context | None) -> dict[str, Any] | None:
        if context is None:
            return None

        nodes = getattr(context, "context", [])
        return {"context": [self.serialize_node(node) for node in nodes]}

    def _parse_uuid(self, value: Any):
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))

    def _parse_datetime(self, value: Any):
        if value is None:
            return datetime.now()
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def _parse_node_status(self, value: Any):
        if isinstance(value, NodeStatus):
            return value
        if isinstance(value, str):
            return NodeStatus[value]
        return NodeStatus(value)

    def _parse_node_type(self, value: Any):
        if isinstance(value, NodeType):
            return value
        if isinstance(value, str):
            return NodeType[value]
        return NodeType(value)

    def deserialize_node(self, payload: dict[str, Any]) -> Node:
        return Node(
            id=self._parse_uuid(payload.get("id")) or uuid4(),
            value=payload.get("value", ""),
            node_status=self._parse_node_status(payload.get("node_status", "pending")),
            node_type=self._parse_node_type(payload.get("node_type", "abstract")),
            created_at=self._parse_datetime(payload.get("created_at")),
            preconditions=payload.get("preconditions") or [],
            effects=payload.get("effects") or [],
            tool_name=payload.get("tool_name"),
            tool_args=payload.get("tool_args"),
            tool_response=payload.get("tool_response"),
            tool_response_summary=payload.get("tool_response_summary"),
            next=self._parse_uuid(payload.get("next")),
            previous=self._parse_uuid(payload.get("previous")),
        )

    def deserialize_context(self, payload: dict[str, Any] | None) -> Context | None:
        if payload is None:
            return None

        raw_nodes = payload.get("context", [])
        nodes = [self.deserialize_node(node_payload) for node_payload in raw_nodes]
        id_map = {node.id: node for node in nodes}

        for node, node_payload in zip(nodes, raw_nodes):
            parent_id = self._parse_uuid(node_payload.get("parent_id"))
            if parent_id and parent_id in id_map:
                node.parent = id_map[parent_id]

            child_ids = node_payload.get("children_ids", [])
            node.children = [
                id_map[child_id]
                for child_id in (self._parse_uuid(raw_id) for raw_id in child_ids)
                if child_id in id_map
            ]

        context = Context()
        context.context = nodes
        return context
