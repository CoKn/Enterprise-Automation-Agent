# planner for generating new planns
import json

from agent.logger import get_logger

from agent.domain.context import Node, Context
from agent.domain.context import NodeStatus
from agent.domain.prompts.planner.planning_prompt import PLANNING_PROMPT
from agent.domain.prompts.planner.replanning_prompt import REPLANNING_PROMPT

from agent.application.ports.outbound.llm_interface import LLM
from agent.application.ports.outbound.context_serializer_interface import ContextSerializer

logger = get_logger(__name__)

class Planner:
    llm: LLM
    serializer: ContextSerializer

    def __init__(self, llm: LLM, serializer: ContextSerializer):
        self.llm = llm
        self.serializer = serializer

    # TODO: question is how tools are processed
    def plan(self, root: Node, context: Context, tool_docs: str = ""):

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
        result: str = self.llm.call(
            prompt=json.dumps(user_payload),
            system_prompt=system_prompt,
            json_mode=True,
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


    def replan(self, root: Node, context: Context, tool_docs: str = ""):
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
        result: str = self.llm.call(
            prompt=json.dumps(user_payload),
            system_prompt=system_prompt,
            json_mode=True,
        )

        logger.info(
            "Replan response: resp='%s'",
            result,
        )

        try:
            # 4. parse response
            replanned = json.loads(result)

            # 5. deserialization -> turn into Context data structure
            replanned_context = self.serializer.deserialize_context(replanned)
            if replanned_context is None:
                raise ValueError("Replanner produced an empty context")

            replanned_root = replanned_context.get_root()
            if replanned_root is None:
                raise ValueError("Replanner produced an empty root")

            existing_node = context.get_node(root.id) or root

            # Repair only the failed node/subtree in place so unrelated branches survive.
            existing_node.value = replanned_root.value
            existing_node.node_status = NodeStatus.pending
            existing_node.node_type = replanned_root.node_type
            existing_node.preconditions = replanned_root.preconditions
            existing_node.effects = replanned_root.effects
            existing_node.tool_name = replanned_root.tool_name
            existing_node.tool_args = replanned_root.tool_args
            existing_node.tool_response = None
            existing_node.tool_response_summary = None
            existing_node.next = replanned_root.next
            existing_node.previous = replanned_root.previous
            existing_node.children = replanned_root.children

            for child in existing_node.children:
                child.parent = existing_node

            # Preserve the original identity of the repaired node.
            existing_node.id = root.id
            existing_node.parent = root.parent

            context.rebuild_indexes()

        except json.JSONDecodeError:
            raise ValueError(f"Planner LLM did not return valid JSON for replan: {result}")

        return context
