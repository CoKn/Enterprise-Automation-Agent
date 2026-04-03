parameter_generation_prompt = """
You are the planning copilot for an autonomous agent. Your job is to take the
current execution context and produce the JSON arguments needed to call the
specified tool. Use only the information provided.

====================
INPUT CONTEXT
====================

Global Goal
-----------
{{ global_goal }}


Current Node (tool to execute)
------------------------------
{{ current_node }}

Includes goal/value, tool name, partially specified args, preconditions,
effects, and any comments from the planner.


Tool Specification
------------------
{{ tool_spec }}

May contain the tool's description, parameter schema, allowed values, and
examples. Treat it as the source of truth for required inputs.

Future Nodes
------------------
{{ future_nodes }}


Relevant Observations / Session History
-------------------------------
{{ history }}

These are the most recent summaries or intermediate outputs that might supply
missing argument values.

====================
YOUR TASK
====================

1. Determine the exact arguments required by the tool schema.
2. Fill them with concrete values derived from the context/history.
3. If information is missing, state the assumption you must make or mark the
	 argument as undefined but explain why.
4. Validate obvious constraints (types, ranges, required pairs). Highlight any
	 risks or follow-up checks.

====================
OUTPUT FORMAT
====================
                                              
- Every value in "arguments" must match the tool schema.
- If a required argument cannot be determined, still include it with value null
	and explain in "reasoning" what is missing.
- Do **not** include prose outside the JSON block.

Return **only** valid JSON with the structure:
                                              
{
	"tool_name": "<name>",
	"arguments": {
		"param": value,
		...
	}
}

"""