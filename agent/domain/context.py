# Data structure to capture steps

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Self
from uuid import UUID, uuid4


class NodeStatus(Enum):
    pending = auto()
    success = auto()
    failed = auto()


class NodeType(Enum):
    abstract = auto()
    parcially_planned = auto()
    fully_planned = auto()


@dataclass
class Node:
    value: str  # holds goal
    id: UUID = field(default_factory=uuid4)
    node_status: NodeStatus = NodeStatus.pending
    node_type: NodeType = NodeType.abstract
    created_at: datetime = field(default_factory=datetime.now)

    # annotations for agent
    preconditions: Optional[list[str]] = field(default_factory=list)
    effects: Optional[list[str]] = field(default_factory=list)

    # tool invocation
    tool_name: Optional[str] = None
    tool_args: Optional[list] = None

    # tool outcome
    tool_response: Optional[str] = None
    tool_response_summary: Optional[str] = None

    # data structure pointer
    parent: Optional[Self] = None
    children: list[Self] = field(default_factory=list)
    next: Optional[UUID] = None
    previous: Optional[UUID] = None

    @property
    def status(self) -> NodeStatus:
        return self.node_status

    @status.setter
    def status(self, value: NodeStatus) -> None:
        self.node_status = value

    @property
    def type(self) -> NodeType:
        return self.node_type

    @type.setter
    def type(self, value: NodeType) -> None:
        self.node_type = value


@dataclass
class Context:
    # a list of root nodes to build the trees from
    context: list[Node] = field(default_factory=list)