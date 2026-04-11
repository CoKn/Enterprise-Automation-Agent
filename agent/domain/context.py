# Data structure to capture steps

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Self, Dict, Set
from uuid import UUID, uuid4


class NodeStatus(Enum):
    pending = auto()
    success = auto()
    failed = auto()


class NodeType(Enum):
    abstract = auto()
    parcially_planned = auto()
    fully_planned = auto()


class TraversalStrategy(Enum):
    tree_bfs = auto()


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

    def to_repr_line(self) -> str:
        return (
            f"- id={self.id} status={self.node_status.name} "
            f"type={self.node_type.name} goal={self.value}"
            f"tool={self.tool_name} tool_args={self.tool_args}"
            f"summary={self.tool_response_summary}"
            f"preconditions={self.preconditions}"
            f"effects={self.effects}"
        )

    def __str__(self) -> str:
        return self.to_repr_line()


@dataclass
class Context:
    roots: list["Node"] = field(default_factory=list)
    traversal_strategy: TraversalStrategy = TraversalStrategy.tree_bfs

    # derived indexes
    node_index: Dict[UUID, "Node"] = field(default_factory=dict, init=False, repr=False)
    root_index: Dict[UUID, "Node"] = field(default_factory=dict, init=False, repr=False)

    def rebuild_indexes(self) -> None:
        self.node_index.clear()
        self.root_index = {root.id: root for root in self.roots}

        visiting: Set[UUID] = set()  # cycle guard

        def walk(node: "Node") -> None:
            if node.id in visiting:
                raise ValueError(f"Cycle detected at node {node.id}")
            if node.id in self.node_index:
                # same node reachable twice = shared subtree / duplicate id problem
                return

            visiting.add(node.id)
            self.node_index[node.id] = node
            for child in node.children:
                walk(child)
            visiting.remove(node.id)

        for root in self.roots:
            walk(root)

    def get_node(self, node_id: UUID) -> "Node | None":
        return self.node_index.get(node_id)

    def add_root(self, root: "Node") -> None:
        self.roots.append(root)
        self.rebuild_indexes()

    def get_root(self) -> Optional[Node]:
        if not self.roots:
            return None
        return self.roots[0]

    def next_node(self, node: Optional[Node]) -> Optional[Node]:
        if node is None:
            return None

        self.rebuild_indexes()

        if self.traversal_strategy == TraversalStrategy.tree_bfs:
            root = self._find_root(node)
            if root is None:
                return None

            ordered_nodes = self._bfs_order(root)
            try:
                idx = ordered_nodes.index(node)
            except ValueError:
                return None

            for candidate in ordered_nodes[idx + 1 :]:
                if candidate.node_type != NodeType.abstract:
                    return candidate
            return None

        return None

    def previous_nodes(self, node: Optional[Node]) -> list[Node]:
        if node is None:
            return []

        self.rebuild_indexes()

        if self.traversal_strategy == TraversalStrategy.tree_bfs:
            root = self._find_root(node)
            if root is None:
                return []

            ordered_nodes = self._bfs_order(root)
            try:
                idx = ordered_nodes.index(node)
            except ValueError:
                return []
            return ordered_nodes[:idx]

        return []

    def next_nodes(self, node: Optional[Node]) -> list[Node]:
        if node is None:
            return []

        self.rebuild_indexes()

        if self.traversal_strategy == TraversalStrategy.tree_bfs:
            root = self._find_root(node)
            if root is None:
                return []

            ordered_nodes = self._bfs_order(root)
            try:
                idx = ordered_nodes.index(node)
            except ValueError:
                return []
            return ordered_nodes[idx + 1 :]

        return []

    def _find_root(self, node: Node) -> Optional[Node]:
        current = node
        while current.parent is not None:
            current = current.parent

        if current.id in self.root_index:
            return current
        return None

    def _bfs_order(self, root: Node) -> list[Node]:
        ordered: list[Node] = []
        queue: list[Node] = [root]
        seen: Set[UUID] = set()

        while queue:
            current = queue.pop(0)
            if current.id in seen:
                continue

            seen.add(current.id)
            ordered.append(current)
            queue.extend(current.children)

        return ordered

    def represent_nodes(self, nodes: list[Node]) -> str:
        if not nodes:
            return ""
        return "\n".join(node.to_repr_line() for node in nodes)

    def recompute_statuses(self) -> None:
        def update(node: Node) -> NodeStatus:
            if not node.children:
                return node.node_status

            child_statuses = [update(child) for child in node.children]
            if any(status == NodeStatus.failed for status in child_statuses):
                node.node_status = NodeStatus.failed
            elif all(status == NodeStatus.success for status in child_statuses):
                node.node_status = NodeStatus.success
            else:
                node.node_status = NodeStatus.pending
            return node.node_status

        for root in self.roots:
            update(root)

    def __str__(self) -> str:
        if not self.roots:
            return "Context(roots=0)"

        self.rebuild_indexes()
        roots = ", ".join(str(root.id) for root in self.roots)
        return f"Context(roots={len(self.roots)}, nodes={len(self.node_index)}, root_ids=[{roots}])"