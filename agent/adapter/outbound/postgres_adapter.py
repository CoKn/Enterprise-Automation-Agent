from __future__ import annotations

import os
import json
from collections import deque
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from agent.adapter.serialization.context import context_to_dict
from agent.application.ports.outbound.memory_interface import Memory
from agent.domain.context import Context, Node


class PostgresAdapter(Memory):
    def __init__(self, dsn: str | None = None, memory_type: str = "episodic") -> None:
        # Accept DSN from constructor first, then env var.
        self._dsn = dsn or os.getenv("POSTGRES_DSN")
        if not self._dsn:
            raise ValueError("Missing PostgreSQL DSN. Provide dsn or set POSTGRES_DSN.")

        self._memory_type = memory_type
        self._conn = psycopg.connect(self._dsn)

    def close(self) -> None:
        if self._conn.closed:
            return
        self._conn.close()

    def save(self, context: Context) -> dict[str, Any]:
        if not context or not context.roots:
            return {"episodes_saved": 0, "nodes_saved": 0}

        episodes_saved = 0
        nodes_saved = 0

        with self._conn.transaction():
            with self._conn.cursor() as cur:
                for root in context.roots:
                    self._upsert_episode(cur=cur, root=root, context=context)
                    episodes_saved += 1

                    bfs_nodes = self._bfs_nodes(root)
                    for idx, node in enumerate(bfs_nodes):
                        path = self._build_path(node=node)
                        sibling_position = 0
                        if node.parent is not None:
                            sibling_position = node.parent.children.index(node)

                        self._upsert_node(
                            cur=cur,
                            episode_id=root.id,
                            node=node,
                            path=path,
                            sibling_position=sibling_position,
                        )
                        self._replace_node_preconditions(cur=cur, node=node)
                        self._replace_node_effects(cur=cur, node=node)
                        nodes_saved += 1

        return {
            "episodes_saved": episodes_saved,
            "nodes_saved": nodes_saved,
            "episode_ids": [str(root.id) for root in context.roots],
        }

    def query(self, goal: str, filter: dict | None = None):
        # TODO: implement retrieval once ranking/reconstruction semantics are defined.
        return []

    def _upsert_episode(self, cur: psycopg.Cursor[Any], root: Node, context: Context) -> None:
        tree_snapshot = context_to_dict(context)
        cur.execute(
            """
            INSERT INTO episodes (
                id, memory_type, root_goal, created_at, finished_at, status, summary, tree_snapshot
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id)
            DO UPDATE SET
                root_goal = EXCLUDED.root_goal,
                finished_at = EXCLUDED.finished_at,
                status = EXCLUDED.status,
                summary = EXCLUDED.summary,
                tree_snapshot = EXCLUDED.tree_snapshot
            """,
            (
                root.id,
                self._memory_type,
                root.value,
                root.created_at,
                None,
                root.node_status.name,
                root.tool_response_summary,
                Jsonb(tree_snapshot),
            ),
        )

    def _upsert_node(
        self,
        cur: psycopg.Cursor[Any],
        episode_id,
        node: Node,
        path: str,
        sibling_position: int,
    ) -> None:
        tool_response_text = self._stringify_tool_response(node.tool_response)

        cur.execute(
            """
            INSERT INTO nodes (
                id,
                episode_id,
                parent_id,
                sibling_position,
                path,
                value,
                node_status,
                node_type,
                created_at,
                tool_name,
                tool_args,
                tool_response,
                tool_response_summary,
                goal_embedding,
                tool_summary_embedding
            )
            VALUES (
                %s, %s, %s, %s, %s::ltree, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL
            )
            ON CONFLICT (id)
            DO UPDATE SET
                parent_id = EXCLUDED.parent_id,
                sibling_position = EXCLUDED.sibling_position,
                path = EXCLUDED.path,
                value = EXCLUDED.value,
                node_status = EXCLUDED.node_status,
                node_type = EXCLUDED.node_type,
                tool_name = EXCLUDED.tool_name,
                tool_args = EXCLUDED.tool_args,
                tool_response = EXCLUDED.tool_response,
                tool_response_summary = EXCLUDED.tool_response_summary
            """,
            (
                node.id,
                episode_id,
                node.parent.id if node.parent is not None else None,
                sibling_position,
                path,
                node.value,
                node.node_status.name,
                node.node_type.name,
                node.created_at,
                node.tool_name,
                Jsonb(node.tool_args) if node.tool_args is not None else None,
                tool_response_text,
                node.tool_response_summary,
            ),
        )

    def _stringify_tool_response(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            return str(value)

    def _replace_node_preconditions(self, cur: psycopg.Cursor[Any], node: Node) -> None:
        cur.execute("DELETE FROM node_preconditions WHERE node_id = %s", (node.id,))
        for position, text in enumerate(node.preconditions or []):
            cur.execute(
                """
                INSERT INTO node_preconditions (node_id, position, text, normalized_text, embedding)
                VALUES (%s, %s, %s, NULL, NULL)
                """,
                (node.id, position, text),
            )

    def _replace_node_effects(self, cur: psycopg.Cursor[Any], node: Node) -> None:
        cur.execute("DELETE FROM node_effects WHERE node_id = %s", (node.id,))
        for position, text in enumerate(node.effects or []):
            cur.execute(
                """
                INSERT INTO node_effects (node_id, position, text, normalized_text, embedding)
                VALUES (%s, %s, %s, NULL, NULL)
                """,
                (node.id, position, text),
            )

    def _build_path(self, node: Node) -> str:
        labels: list[str] = []
        cursor = node
        while cursor is not None:
            labels.append(f"n_{str(cursor.id).replace('-', '')}")
            cursor = cursor.parent
        labels.reverse()
        return ".".join(labels)

    def _bfs_nodes(self, root: Node) -> list[Node]:
        ordered: list[Node] = []
        queue: deque[Node] = deque([root])
        while queue:
            current = queue.popleft()
            ordered.append(current)
            for child in current.children:
                queue.append(child)
        return ordered