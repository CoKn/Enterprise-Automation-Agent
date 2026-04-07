# planner for generating new planns
import json

from agent.domain.context import Node, Context
from agent.domain.prompts.planner.planning_prompt import PLANNING_PROMPT
from agent.application.ports.outbound.llm_interface import LLM
from agent.application.ports.outbound.context_serializer_interface import ContextSerializer


class Planner:
    llm: LLM
    serializer: ContextSerializer

    def __init__(self, llm: LLM, serializer: ContextSerializer):
        self.llm = llm
        self.serializer = serializer

    # TODO: question is how tools are processed
    def plan(self, root: Node, context: Context, tool_docs: str):

        # 1. load planning prompt and format prompt (takes: root node, tool specs, context (for episodic memory and previous nodes))
        system_prompt = PLANNING_PROMPT.format(tool_docs=tool_docs or "")

        # 2. serialize root and context and create payload
        root_payload = self.serializer.serialize_node(root)

        # TODO: check if complete tree is serialized
        context_payload = self.serializer.serialize_context(context)

        user_payload = {
            "goal": root.value,
            "root": root_payload,
            "context": context_payload,
        }

        # 3. send prompt to LLM
        result: str = self.llm.call(
            prompt=json.dumps(user_payload),
            system_prompt=system_prompt,
            json_mode=True,
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


