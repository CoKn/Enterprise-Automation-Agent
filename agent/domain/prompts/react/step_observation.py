step_observation_prompt = """
You are observing the execution of a single tool call that is part of a larger, structured plan.
Use the information below to understand the context and then generate a concise, structured
observation about what just happened and how it affects the plan.

====================
INPUT CONTEXT
====================

Global Goal
-----------
{{ global_goal }}


Previous Nodes (already executed)
---------------------------------
{{ previous_nodes }}

Each previous node may contain:
- goal / node value
- tool name
- tool args
- tool docs (if available)
- tool response / tool response summary
- pre conditions
- effects


Next Nodes (planned / not yet executed)
---------------------------------------
{{ next_nodes }}

Each next node may contain:
- goal / node value
- tool name
- tool args
- tool docs
- pre conditions
- effects


Current Node (just executed)
---------------------------
{{ current_node }}

The current node may contain:
- goal / node value
- tool name
- tool args
- tool docs
- full tool response
- pre conditions
- effects

====================
YOUR TASK
====================

Based on the context above, write an observation that:
1. Summarises what the current tool just did and what its response means.
2. Explains how the current node contributes to the global goal.
3. Describes how this step changes or informs the remaining plan (next nodes).
4. Highlights any important new information, decisions, risks, or follow-up actions.
5. Answers the goal of the current node with explicit values.

Follow these guidelines:
- Only use information provided in the inputs; do not invent tools, data, or results.
- If something is missing or unclear, state that explicitly instead of guessing.
- Focus on what is relevant for guiding subsequent planning and tool choices.

====================
OUTPUT FORMAT
====================

Return ONLY valid JSON as a dictionary with exactly these two properties:

{
	"has_error": boolean,
	"summary": string
}

Rules for `has_error`:
- Set to true when the current tool response indicates an error or failure.
- Set to false otherwise.

Rules for `summary`:
- Use plain text.
- Include these sections in order:
	1. Summary of Current Tool
	2. Relation to Global Goal
	3. Impact on Plan / Next Nodes
	4. Key Insights and Follow-ups
	5. Answered Current Goal
- In "Answered Current Goal", provide explicit values requested by the current node goal.
- If explicit values are missing, clearly state what is missing.

Do not return markdown code fences.

"""