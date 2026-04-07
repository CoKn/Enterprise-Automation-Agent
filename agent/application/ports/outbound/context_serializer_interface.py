from abc import ABC, abstractmethod
from typing import Any

from agent.domain.context import Context, Node


class ContextSerializer(ABC):
    @abstractmethod
    def serialize_node(self, node: Node) -> dict[str, Any]:
        ...

    @abstractmethod
    def serialize_context(self, context: Context | None) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def deserialize_node(self, payload: dict[str, Any]) -> Node:
        ...

    @abstractmethod
    def deserialize_context(self, payload: dict[str, Any] | None) -> Context | None:
        ...
