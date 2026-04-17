REFLECTION_PROMPT = """
You are a procedural reflection engine for an autonomous agent.

Your task is to synthesize a reusable procedural context tree from a finished execution trace.

CRITICAL SCOPE RULES:
- Use ONLY successful tool invocations provided in the input as reflection evidence.
- Never include failed tool invocations in the resulting procedural tree.
- Never fabricate tool names, arguments, IDs, or outcomes.

STABILITY JUDGMENT RULES FOR tool_args:
- Stable arguments: values reusable across many runs in similar environments.
  Examples: clicking a named button, selecting a stable menu path, a static workspace URL,
  deterministic configuration flags.
- Unstable arguments: values depending on runtime-specific outputs from previous steps.
  Examples: ephemeral IDs, run-specific timestamps, temporary tokens, dynamically created object IDs.
- In reflected nodes, keep stable args in tool_args.
- Remove unstable args from tool_args and explain how to re-acquire them in annotation.

ANNOTATION RULES:
- Every node must include annotation.
- annotation must contain concise, practical tool-usage hints:
  - when to use this tool step,
  - how to execute it reliably,
  - which args are stable vs unstable,
  - prerequisites and expected effects.
- If unstable args were removed, annotation must explicitly state which values are dynamic
  and what preceding evidence/step is needed to obtain them.

INPUT
-----

Global Goal:
{{ global_goal }}

Entire Context Tree (full trace, for structure and dependency understanding):
{{ full_context_tree }}

OUTPUT REQUIREMENTS:
- Return valid JSON only.
- Return exactly one top-level key: root
- root must be a Node-like tree.
- Do not include markdown code fences.

Each node should include these properties:
- value
- node_status
- node_type
- preconditions
- effects
- tool_name
- tool_args
- annotation
- children

Output JSON schema shape:
{
	"root": {
		"value": "...",
		"node_status": "pending|success|failed",
		"node_type": "abstract|parcially_planned|fully_planned",
		"preconditions": ["..."],
		"effects": ["..."],
		"tool_name": "... or null",
		"tool_args": {"arg": "value"} or null,
		"annotation": "tool usage hints including stable vs unstable args",
		"children": [ ...same node schema... ]
	}
}
""".strip()
