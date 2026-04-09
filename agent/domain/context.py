# Data structure to capture steps

from dataclasses import dataclass, field
from uuid import uuid4
from typing import Optional, Self
from enum import Enum, auto
from datetime import datetime


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
    id: uuid4 = field(default_factory=uuid4)
    value: str  # holds goal
    node_status: NodeStatus = NodeStatus.pending
    node_type: NodeType = NodeType.abstract
    created_at: datetime = field(default_factory=datetime.now)

    # annotations for agent
    preconditions: Optional[list[str]] = field(default_factory=list)
    effects: Optional[list[str]] = field(default_factory=list)

    # tool invocation
    tool_name: Optional[str]
    tool_args: Optional[list]

    # tool outcome
    tool_response: Optional[str]
    tool_response_summary: Optional[str]

    # data structure pointer
    parent: Optional[Self] = None
    children: list[Self] = field(default_factory=list)
    next: Optional[uuid4] = None
    previous: Optional[uuid4] = None


class Context:
    # a list of root nodes to build the trees from
    context: list[Node]