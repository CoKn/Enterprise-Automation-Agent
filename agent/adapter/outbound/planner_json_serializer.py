from dataclasses import is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from agent.application.ports.outbound.context_serializer_interface import ContextSerializer
from agent.domain.context import Context, Node, NodeStatus, NodeType


class ContextJsonSerializer(ContextSerializer):
    def _flatten_nodes_from_roots(self, roots: list[Node]) -> list[Node]:
        result: list[Node] = []
        seen: set[UUID] = set()
        queue: list[Node] = list(roots)

        while queue:
            node = queue.pop(0)
            if node.id in seen:
                continue

            seen.add(node.id)
            result.append(node)
            queue.extend(node.children)

        return result

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
        if hasattr(value, "__dict__"):
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
            "annotation": node.annotation,
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

        nodes = self._flatten_nodes_from_roots(context.roots)
        return {
            "context": [self.serialize_node(node) for node in nodes],
            "root_ids": [self._to_jsonable(root.id) for root in context.roots],
        }

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
            if value == "completed":
                return NodeStatus.success
            return NodeStatus[value]
        return NodeStatus(value)

    def _parse_node_type(self, value: Any):
        if isinstance(value, NodeType):
            return value
        if isinstance(value, str):
            return NodeType[value]
        return NodeType(value)

    def _parse_link_uuid(self, value: Any):
        if isinstance(value, dict):
            value = value.get("id")
        return self._parse_uuid(value)

    def deserialize_node(self, payload: dict[str, Any]) -> Node:
        return Node(
            id=self._parse_uuid(payload.get("id")) or uuid4(),
            value=payload.get("value", ""),
            node_status=self._parse_node_status(payload.get("node_status", payload.get("status", "pending"))),
            node_type=self._parse_node_type(payload.get("node_type", payload.get("type", "abstract"))),
            created_at=self._parse_datetime(payload.get("created_at")),
            preconditions=payload.get("preconditions") or [],
            effects=payload.get("effects") or [],
            tool_name=payload.get("tool_name"),
            tool_args=payload.get("tool_args"),
            annotation=payload.get("annotation") or "",
            tool_response=payload.get("tool_response"),
            tool_response_summary=payload.get("tool_response_summary"),
            next=self._parse_link_uuid(payload.get("next")),
            previous=self._parse_link_uuid(payload.get("previous")),
        )

    def _deserialize_tree_node(self, payload: dict[str, Any], parent: Node | None = None) -> Node:
        node = self.deserialize_node(payload)
        node.parent = parent

        raw_children = payload.get("children") or []
        children: list[Node] = []
        for child_payload in raw_children:
            if not isinstance(child_payload, dict):
                continue
            children.append(self._deserialize_tree_node(child_payload, parent=node))
        node.children = children

        return node

    def deserialize_context(self, payload: dict[str, Any] | None) -> Context | None:
        if payload is None:
            return None

        # Accept planner output as nested tree payload: {"root": {...}}
        raw_root = payload.get("root")
        if isinstance(raw_root, dict):
            root = self._deserialize_tree_node(raw_root)
            context = Context(roots=[root])
            context.rebuild_indexes()
            return context

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

        raw_root_ids = payload.get("root_ids", [])
        parsed_root_ids = [self._parse_uuid(root_id) for root_id in raw_root_ids]

        roots = [id_map[root_id] for root_id in parsed_root_ids if root_id in id_map]
        if not roots:
            roots = [node for node in nodes if node.parent is None]

        context = Context(roots=roots)
        context.rebuild_indexes()
        return context
