# planner for generating new planns
import json
from datetime import datetime
from uuid import uuid4
from typing import Optional

from agent.logger import get_logger

from agent.domain.context import Node, Context
from agent.domain.context import NodeStatus
from agent.domain.prompts.planner.planning_prompt import PLANNING_PROMPT
from agent.domain.prompts.planner.replanning_prompt import REPLANNING_PROMPT

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

    # TODO: question is how tools are processed
    def plan(self, root: Node, context: Context, tool_docs: str = "", run_id: str | None = None):

        # 1. load planning prompt and format prompt (takes: root node, tool specs, context (for episodic memory and previous nodes))
        system_prompt = PLANNING_PROMPT.format(tool_docs=tool_docs)

        # 2. serialize root and context and create payload
        root_payload = self.serializer.serialize_node(root)

        # TODO: check if complete tree is serialized
        context_payload = self.serializer.serialize_context(context)

        user_payload = {
            "goal": root.value,
            "root": root_payload,
            "context": context_payload,
        }

        logger.info(
            "Userpayload: goal='%(goal)s' root=%(root)s context=%(context)s",
            user_payload,
        )

        # 3. send prompt to LLM
        llm_result = self.llm.call(
            prompt=json.dumps(user_payload),
            system_prompt=system_prompt,
            json_mode=True,
        )

        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        result: str = llm_result.get("response") or ""

        if self.analytics and run_id:
            self.analytics.save_call(
            run_id=run_id,
                phase="plan",
                model=str(llm_result.get("model") or "unknown"),
                provider=str(llm_result.get("provider") or "unknown"),
                prompt_tokens=int(llm_result.get("prompt_tokens") or 0),
                completion_tokens=int(llm_result.get("completion_tokens") or 0),
                total_tokens=int(llm_result.get("total_tokens") or 0),
                created_at=datetime.now(),
            )

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

        return context_result


    def replan(self, root: Node, context: Context, tool_docs: str = "", run_id: str | None = None):
        # 1. load replanning prompt and format with available tools
        system_prompt = REPLANNING_PROMPT.format(tool_docs=tool_docs)

        # 2. serialize failed root and full context
        root_payload = self.serializer.serialize_node(root)
        context_payload = self.serializer.serialize_context(context)

        user_payload = {
            "goal": root.value,
            "failed_node": root_payload,
            "context": context_payload,
        }

        logger.info(
            "Replan userpayload: goal='%(goal)s' failed_node=%(failed_node)s context=%(context)s",
            user_payload,
        )

        # 3. send prompt to LLM
        llm_result = self.llm.call(
            prompt=json.dumps(user_payload),
            system_prompt=system_prompt,
            json_mode=True,
        )

        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        result: str = llm_result.get("response") or ""

        if self.analytics and run_id:
            self.analytics.save_call(
            run_id=run_id,
                phase="replan",
                model=str(llm_result.get("model") or "unknown"),
                provider=str(llm_result.get("provider") or "unknown"),
                prompt_tokens=int(llm_result.get("prompt_tokens") or 0),
                completion_tokens=int(llm_result.get("completion_tokens") or 0),
                total_tokens=int(llm_result.get("total_tokens") or 0),
                created_at=datetime.now(),
            )

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
            # 4. parse response
            replanned = json.loads(result)

            insertion_payload = None
            if isinstance(replanned, dict):
                if isinstance(replanned.get("node"), dict):
                    insertion_payload = replanned.get("node")
                elif isinstance(replanned.get("root"), dict):
                    # Backward compatibility for older prompt outputs.
                    insertion_payload = replanned.get("root")

            if not isinstance(insertion_payload, dict):
                raise ValueError("Replanner output must include a single node under key 'node'")

            insertion_node = self.serializer.deserialize_node(insertion_payload)
            insertion_node.id = insertion_node.id or uuid4()
            insertion_node.node_status = NodeStatus.pending
            insertion_node.tool_response = None
            insertion_node.tool_response_summary = None

            failed_node = context.get_node(root.id) or root
            parent = failed_node.parent

            if parent is not None:
                siblings = parent.children
                idx = next((i for i, n in enumerate(siblings) if n.id == failed_node.id), -1)
                old_next = siblings[idx + 1] if idx >= 0 and idx + 1 < len(siblings) else None

                insertion_node.parent = parent
                if idx >= 0:
                    siblings.insert(idx + 1, insertion_node)
                else:
                    siblings.append(insertion_node)
            else:
                roots = context.roots
                idx = next((i for i, n in enumerate(roots) if n.id == failed_node.id), -1)
                old_next = roots[idx + 1] if idx >= 0 and idx + 1 < len(roots) else None

                insertion_node.parent = None
                if idx >= 0:
                    roots.insert(idx + 1, insertion_node)
                else:
                    roots.append(insertion_node)

            insertion_node.previous = failed_node.id
            insertion_node.next = old_next.id if old_next is not None else None
            failed_node.next = insertion_node.id
            if old_next is not None:
                old_next.previous = insertion_node.id

            context.rebuild_indexes()

        except json.JSONDecodeError:
            raise ValueError(f"Planner LLM did not return valid JSON for replan: {result}")

        return context
