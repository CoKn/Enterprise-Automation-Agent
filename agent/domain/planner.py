# planner for generating new planns
from __future__ import annotations
import json
from uuid import uuid4
from typing import Optional

from agent.logger import get_logger

from agent.domain.context import Context, Node, NodeStatus


from agent.application.ports.outbound.llm_interface import LLM
from agent.application.ports.outbound.context_serializer_interface import ContextSerializer
from agent.application.ports.outbound.analytics_db_interface import AnalyticsDB

logger = get_logger(__name__)

class Planner:
    llm: LLM
    serializer: ContextSerializer
    analytics: Optional[AnalyticsDB]

    def __init__(self, llm: LLM, serializer: ContextSerializer, analytics: Optional[AnalyticsDB] = None):
        self.llm = llm
        self.serializer = serializer
        self.analytics = analytics


    def plan(self, prompt: str):

        # 1. send prompt to LLM (single combined prompt string)
        llm_result = self.llm.call(
            prompt=prompt,
            json_mode=True,
        )

        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        result: str = llm_result.get("response") or ""

        logger.info(
            "LLM usage phase=plan prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            llm_result.get("prompt_tokens", 0),
            llm_result.get("completion_tokens", 0),
            llm_result.get("total_tokens", 0),
        )

        logger.info(
            "Response: resp='%s'",
            result,
        )

        try:
            # 4. parse response
            plan = json.loads(result)

            # 5. deserilisation -> turn into Context data structure
            context_result = self.serializer.deserialize_context(plan)
            if context_result is None:
                raise ValueError("Planner produced an empty context")

        except json.JSONDecodeError:
            raise ValueError(f"Planner LLM did not return valid JSON: {result}")

        return context_result, llm_result


    def extend_plan(self, prompt: str):

        llm_result = self.llm.call(
            prompt=prompt,
            json_mode=True,
        )

        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        result: str = llm_result.get("response") or ""

        logger.info(
            "LLM usage phase=extend_plan prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            llm_result.get("prompt_tokens", 0),
            llm_result.get("completion_tokens", 0),
            llm_result.get("total_tokens", 0),
        )

        logger.info(
            "Extend response: resp='%s'",
            result,
        )

        try:
            extension_payload = json.loads(result)
            extension_context = self.serializer.deserialize_context(extension_payload)
            if extension_context is None:
                raise ValueError("Planner extension produced an empty context")

            extension_root = extension_context.get_root()
            if extension_root is None:
                raise ValueError("Planner extension produced no root")

        except json.JSONDecodeError:
            raise ValueError(f"Planner extension did not return valid JSON: {result}")

        return extension_root, llm_result


    def replan(self, prompt: str, context: Context, failed_node: Node):

        # 1. send prompt to LLM
        llm_result = self.llm.call(
            prompt=prompt,
            json_mode=True,
        )

        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        result: str = llm_result.get("response") or ""

        logger.info(
            "LLM usage phase=replan prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            llm_result.get("prompt_tokens", 0),
            llm_result.get("completion_tokens", 0),
            llm_result.get("total_tokens", 0),
        )

        logger.info(
            "Replan response: resp='%s'",
            result,
        )

        try:
            # 2. parse response
            replanned = json.loads(result)

            insertion_payload = replanned.get("node", None)

            if not isinstance(insertion_payload, dict):
                raise ValueError("Replanner output must include a single node under key 'node'")

            insertion_node = self.serializer.deserialize_node(insertion_payload)
            insertion_node.id = insertion_node.id or uuid4()
            insertion_node.node_status = NodeStatus.pending
            insertion_node.cached = False
            insertion_node.tool_response = None
            insertion_node.tool_response_summary = None

            context.rebuild_indexes()
            failed = context.get_node(failed_node.id) or failed_node
            parent = failed.parent

            if parent is not None:
                siblings = parent.children
                idx = next((i for i, n in enumerate(siblings) if n.id == failed.id), -1)
                old_next = siblings[idx + 1] if idx >= 0 and idx + 1 < len(siblings) else None

                insertion_node.parent = parent
                if idx >= 0:
                    siblings.insert(idx + 1, insertion_node)
                else:
                    siblings.append(insertion_node)
            else:
                roots = context.roots
                idx = next((i for i, n in enumerate(roots) if n.id == failed.id), -1)
                old_next = roots[idx + 1] if idx >= 0 and idx + 1 < len(roots) else None

                insertion_node.parent = None
                if idx >= 0:
                    roots.insert(idx + 1, insertion_node)
                else:
                    roots.append(insertion_node)

            insertion_node.previous = failed.id
            insertion_node.next = old_next.id if old_next is not None else None
            failed.next = insertion_node.id
            if old_next is not None:
                old_next.previous = insertion_node.id

            context.rebuild_indexes()

        except json.JSONDecodeError:
            raise ValueError(f"Planner LLM did not return valid JSON for replan: {result}")

        return context, llm_result
