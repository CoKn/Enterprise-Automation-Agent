
import json
import os
from typing import Any, Dict, Optional

import chromadb
from chromadb.config import Settings

from agent.adapter.serialization.context import context_to_dict, flatten_nodes
from agent.adapter.deserialization.context import context_from_dict
from agent.application.ports.outbound.memory_interface import Memory
from agent.domain.context import Context


class ChromadbAdapter(Memory):
    client: None
    _COLLECTIONS = {
        "nodes_value",
        "nodes_summary",
        "nodes_preconditions",
        "nodes_effects",
    }
    _KNOWN_MEMORY_TYPES = {"episodic", "procedural", "semantic"}

    def __init__(
        self,
        path: str,
        client_settings: Optional[Settings] = Settings(anonymized_telemetry=False),
    ):
        super().__init__()
        resolved_path = os.getenv("CHROMADB") or path or "data"
        self.client = chromadb.PersistentClient(path=resolved_path, settings=client_settings)

    def _normalize_goal(self, text: str) -> str:
        return " ".join(text.strip().lower().split())

    def _merge_where(self, *clauses: dict | None) -> dict | None:
        parts = [clause for clause in clauses if clause]
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return {"$and": parts}

    def _materialized_path(self, node_id: str, parent_lookup: Dict[str, Optional[str]]) -> str:
        lineage: list[str] = []
        current: Optional[str] = node_id
        visited: set[str] = set()

        while current and current not in visited:
            lineage.append(current)
            visited.add(current)
            current = parent_lookup.get(current)

        lineage.reverse()
        return "/".join(lineage)

    def _resolve_collection_name(self, filter: dict | None) -> str | None:
        if not filter:
            return "nodes_value"
        candidate = filter.get("collection") or filter.get("search_by") or "nodes_value"
        candidate = str(candidate).strip()
        return candidate if candidate in self._COLLECTIONS else None

    def _extract_node_id_from_record_id(self, record_id: str) -> str:
        raw_id = str(record_id)
        parts = raw_id.split(":")

        # New composite IDs are namespaced as: <memory_type>:<node_id>[:kind[:position]].
        if len(parts) >= 2 and parts[0] in self._KNOWN_MEMORY_TYPES:
            return parts[1]

        # Backward compatibility with older IDs like <node_id>:summary.
        return parts[0]

    def _build_node_dict_from_metadata(
        self,
        node_id: str,
        memory_type: str | None = None,
    ) -> Dict[str, Any] | None:
        """Build a single node dict from database metadata."""
        value_collection = self.client.get_or_create_collection(name="nodes_value")
        summary_collection = self.client.get_or_create_collection(name="nodes_summary")
        preconditions_collection = self.client.get_or_create_collection(name="nodes_preconditions")
        effects_collection = self.client.get_or_create_collection(name="nodes_effects")

        node_where: Dict[str, Any] | None = {"id": node_id}
        if memory_type:
            node_where = {
                "$and": [
                    {"id": node_id},
                    {"memory_type": memory_type},
                ]
            }

        value_rows = value_collection.get(where=node_where, include=["documents", "metadatas"])
        value_docs = value_rows.get("documents") or []
        value_metas = value_rows.get("metadatas") or []

        if not value_docs:
            return None

        base_metadata = value_metas[0] if value_metas and isinstance(value_metas[0], dict) else {}

        summary_rows = summary_collection.get(where=node_where, include=["documents", "metadatas"])
        summary_docs = [d for d in (summary_rows.get("documents") or []) if isinstance(d, str) and d.strip()]
        summary_text = summary_docs[0] if summary_docs else base_metadata.get("tool_summary")

        raw_tool_args = base_metadata.get("tool_args")
        parsed_tool_args: Dict[str, Any] | None = None
        if isinstance(raw_tool_args, dict):
            parsed_tool_args = raw_tool_args
        elif isinstance(raw_tool_args, str) and raw_tool_args.strip():
            try:
                loaded_tool_args = json.loads(raw_tool_args)
                if isinstance(loaded_tool_args, dict):
                    parsed_tool_args = loaded_tool_args
            except json.JSONDecodeError:
                parsed_tool_args = None

        precondition_rows = preconditions_collection.get(where=node_where, include=["documents", "metadatas"])
        precondition_docs = [
            d for d in (precondition_rows.get("documents") or []) if isinstance(d, str)
        ]

        effect_rows = effects_collection.get(where=node_where, include=["documents", "metadatas"])
        effect_docs = [d for d in (effect_rows.get("documents") or []) if isinstance(d, str)]

        node_dict: Dict[str, Any] = {
            "id": base_metadata.get("id") or node_id,
            "value": value_docs[0],
            "status": base_metadata.get("status") or "pending",
            "type": base_metadata.get("type") or "abstract",
            "cached": bool(base_metadata.get("cached", False)),
            "created_at": base_metadata.get("created_at"),
            "tool_name": base_metadata.get("tool_name"),
            "tool_args": parsed_tool_args,
            "annotation": base_metadata.get("annotation") or "",
            "tool_response_summary": summary_text,
            "preconditions": precondition_docs,
            "effects": effect_docs,
            "next": base_metadata.get("next"),
            "previous": base_metadata.get("previous"),
            "children": [],
        }
        return node_dict

    def _build_context_from_node_id(self, node_id: str, memory_type: str | None = None) -> Context:
        """Rebuild subtree starting from the queried node as root."""
        # Recursively build the tree starting from the queried node
        def build_node_tree(nid: str) -> Dict[str, Any] | None:
            node_dict = self._build_node_dict_from_metadata(nid, memory_type=memory_type)
            if not node_dict:
                return None

            # Find all children of this node by querying for nodes where parent_id == nid
            value_collection = self.client.get_or_create_collection(name="nodes_value")

            child_where: Dict[str, Any] | None = {"parent_id": nid}
            if memory_type:
                child_where = {
                    "$and": [
                        {"parent_id": nid},
                        {"memory_type": memory_type},
                    ]
                }

            children_rows = value_collection.get(
                where=child_where,
                include=["metadatas"]
            )
            children_metas = children_rows.get("metadatas") or []

            # Recursively build each child
            children = []
            for child_meta in children_metas:
                if isinstance(child_meta, dict):
                    child_id = child_meta.get("id")
                    if child_id:
                        child_tree = build_node_tree(child_id)
                        if child_tree:
                            children.append(child_tree)

            node_dict["children"] = children
            return node_dict

        root_dict = build_node_tree(node_id)
        if not root_dict:
            return Context()

        context = context_from_dict(root_dict)
        context.rebuild_indexes()

        # Nodes reconstructed from memory are reused nodes.
        for node in context.node_index.values():
            node.cached = True

        return context

    def save(self, context: Context, memory_type: str = "episodic"):
        nodes_value = self.client.get_or_create_collection(name="nodes_value")
        nodes_summary = self.client.get_or_create_collection(name="nodes_summary")
        nodes_preconditions = self.client.get_or_create_collection(name="nodes_preconditions")
        nodes_effects = self.client.get_or_create_collection(name="nodes_effects")
        memory_scope = str(memory_type).strip() if memory_type else "episodic"

        if not (serialized_context := context_to_dict(context=context)):
            return {
                "nodes_value": 0,
                "nodes_summary": 0,
                "nodes_preconditions": 0,
                "nodes_effects": 0,
            }

        flat_nodes = list(flatten_nodes(serialized_context))

        parent_lookup: Dict[str, Optional[str]] = {}
        for node in flat_nodes:
            node_id = node.get("id")
            if node_id:
                parent_lookup[node_id] = node.get("parent_id") or None

        value_documents: list[str] = []
        value_metadatas: list[Dict[str, Any]] = []
        value_ids: list[str] = []

        summary_documents: list[str] = []
        summary_metadatas: list[Dict[str, Any]] = []
        summary_ids: list[str] = []

        precondition_documents: list[str] = []
        precondition_metadatas: list[Dict[str, Any]] = []
        precondition_ids: list[str] = []

        effect_documents: list[str] = []
        effect_metadatas: list[Dict[str, Any]] = []
        effect_ids: list[str] = []

        for node in flat_nodes:
            node_id = node.get("id")
            if not node_id:
                continue

            parent_id = node.get("parent_id") or None
            descendant_of = self._materialized_path(node_id=node_id, parent_lookup=parent_lookup)

            tool_response = node.get("tool_response") or {}
            tool_args_raw = node.get("tool_args")
            tool_args_json = (
                json.dumps(tool_args_raw, default=str) if tool_args_raw is not None else None
            )

            goal_text = node.get("value")
            normalized_value = (
                self._normalize_goal(goal_text)
                if isinstance(goal_text, str) and goal_text.strip()
                else None
            )

            base_metadata: Dict[str, Any] = {
                "id": node_id,
                "tool_name": node.get("tool_name") or None,
                "annotation": node.get("annotation") or "",
                "tool_summary": node.get("tool_response_summary") or None,
                "cached": bool(node.get("cached", False)),
                "tool_response_text": (
                    tool_response.get("text") if isinstance(tool_response, dict) else str(tool_response)
                ),
                "tool_response_structured": (
                    json.dumps(tool_response.get("structured"), default=str)
                    if isinstance(tool_response, dict) and tool_response.get("structured") is not None
                    else None
                ),
                "tool_args": tool_args_json,
                "type": node.get("type"),
                "status": node.get("status"),
                "created_at": node.get("created_at"),
                "next": node.get("next") or None,
                "previous": node.get("previous") or None,
                "parent_id": parent_id,
                "descendant_of": descendant_of,
                "memory_type": memory_scope,
                "is_root": parent_id is None,
                "normalized_value": normalized_value,
            }

            goal_text = node.get("value")
            if isinstance(goal_text, str) and goal_text.strip():
                value_documents.append(goal_text)
                value_ids.append(f"{memory_scope}:{node_id}")
                value_metadatas.append({**base_metadata, "kind": "goal"})

            summary_text = node.get("tool_response_summary")
            if isinstance(summary_text, str) and summary_text.strip():
                summary_documents.append(summary_text)
                summary_ids.append(f"{memory_scope}:{node_id}:summary")
                summary_metadatas.append({**base_metadata, "kind": "summary"})

            for idx, precondition in enumerate(node.get("preconditions") or []):
                if not isinstance(precondition, str) or not precondition.strip():
                    continue
                precondition_documents.append(precondition)
                precondition_ids.append(f"{memory_scope}:{node_id}:precondition:{idx}")
                precondition_metadatas.append(
                    {
                        **base_metadata,
                        "kind": "precondition",
                        "position": idx,
                    }
                )

            for idx, effect in enumerate(node.get("effects") or []):
                if not isinstance(effect, str) or not effect.strip():
                    continue
                effect_documents.append(effect)
                effect_ids.append(f"{memory_scope}:{node_id}:effect:{idx}")
                effect_metadatas.append(
                    {
                        **base_metadata,
                        "kind": "effect",
                        "position": idx,
                    }
                )

        if value_documents:
            nodes_value.upsert(documents=value_documents, ids=value_ids, metadatas=value_metadatas)

        if summary_documents:
            nodes_summary.upsert(
                documents=summary_documents,
                ids=summary_ids,
                metadatas=summary_metadatas,
            )

        if precondition_documents:
            nodes_preconditions.upsert(
                documents=precondition_documents,
                ids=precondition_ids,
                metadatas=precondition_metadatas,
            )

        if effect_documents:
            nodes_effects.upsert(
                documents=effect_documents,
                ids=effect_ids,
                metadatas=effect_metadatas,
            )

        return {
            "nodes_value": len(value_documents),
            "nodes_summary": len(summary_documents),
            "nodes_preconditions": len(precondition_documents),
            "nodes_effects": len(effect_documents),
        }
    


    def query(
        self,
        value: str,
        filter: dict | None = None,
        memory_type: str | None = None,
    ) -> Context | None:
        if not value or not value.strip():
            return None

        collection_name = self._resolve_collection_name(filter)
        if not collection_name:
            return None

        n_results = 1
        where: Dict[str, Any] | None = None
        max_distance: float | None = None
        root_only = False
        prefer_abstract = False
        include: list[str] = ["documents", "metadatas", "distances"]

        if filter:
            raw_n_results = filter.get("n_results")
            if isinstance(raw_n_results, int) and raw_n_results > 0:
                n_results = raw_n_results
            raw_max_distance = filter.get("max_distance")
            if isinstance(raw_max_distance, (int, float)):
                max_distance = float(raw_max_distance)
            root_only = bool(filter.get("root_only", False))
            prefer_abstract = bool(filter.get("prefer_abstract", False))
            raw_where = filter.get("where")
            if isinstance(raw_where, dict):
                where = raw_where

        if memory_type:
            where = self._merge_where(where, {"memory_type": memory_type})

        if root_only:
            where = self._merge_where(where, {"is_root": True})

        if prefer_abstract:
            where = self._merge_where(where, {"type": "abstract"})

        collection = self.client.get_or_create_collection(name=collection_name)

        if collection_name == "nodes_value":
            exact_where = self._merge_where(
                where,
                {"normalized_value": self._normalize_goal(value)},
            )
            exact_result = collection.get(where=exact_where, include=["metadatas"])
            exact_metas = exact_result.get("metadatas") or []

            if exact_metas:
                exact_meta = exact_metas[0]
                if isinstance(exact_meta, dict):
                    node_id = exact_meta.get("id")
                    if node_id:
                        return self._build_context_from_node_id(node_id, memory_type=memory_type)

        result = collection.query(
            query_texts=[value],
            n_results=n_results,
            where=where,
            include=include,
        )

        ids_rows = result.get("ids") or []
        metas_rows = result.get("metadatas") or []
        distances_rows = result.get("distances") or []
        ids = ids_rows[0] if ids_rows and isinstance(ids_rows[0], list) else []
        metas = metas_rows[0] if metas_rows and isinstance(metas_rows[0], list) else []
        distances = (
            distances_rows[0] if distances_rows and isinstance(distances_rows[0], list) else []
        )

        candidate_indices = list(range(len(ids)))

        if max_distance is not None:
            candidate_indices = [
                idx
                for idx in candidate_indices
                if idx < len(distances)
                and isinstance(distances[idx], (int, float))
                and float(distances[idx]) <= max_distance
            ]
            if not candidate_indices:
                return None

        selected_idx = candidate_indices[0] if candidate_indices else None
        if selected_idx is None:
            return None

        node_id: str | None = None
        selected_meta = metas[selected_idx] if selected_idx < len(metas) and isinstance(metas[selected_idx], dict) else {}
        if selected_meta:
            metadata_id = selected_meta.get("id")
            if metadata_id:
                node_id = str(metadata_id)

        if not node_id and selected_idx < len(ids):
            node_id = self._extract_node_id_from_record_id(str(ids[selected_idx]))

        if not node_id:
            return None

        return self._build_context_from_node_id(node_id, memory_type=memory_type)