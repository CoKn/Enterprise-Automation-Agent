step_observation_prompt = """
You are observing the execution of a single tool call that is part of a larger, structured plan.
Your job is not only to summarize what happened, but also to extract and preserve any concrete
values that may be needed by later planned tool calls.

You must treat future tool arguments as tracked plan parameters ("slots").
Whenever the current tool response contains enough evidence to fill one of these slots, you must
return the exact value in structured form.

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
- id
- goal / node value
- tool name
- tool args
- tool docs (if available)
- tool response / tool response summary
- preconditions
- effects


Next Nodes (planned / not yet executed)
---------------------------------------
{{ next_nodes }}

Each next node may contain:
- id
- goal / node value
- tool name
- tool args
- tool docs
- preconditions
- effects


Tracked Plan Parameters / Future Tool Arguments
-----------------------------------------------
{{ tracked_parameters }}

This section is dynamically generated from the plan.
Each tracked item may contain:
- binding_key: a stable identifier for the value to track
- target_node_id: the id of the future node that should be updated
- future_node_goal: goal of the future node that needs this value
- tool_name: name of the future tool that will need the value
- arg_name: exact tool argument name to fill
- description: what this value represents
- current_value: current known value, or null if unresolved

Your task is to update these tracked parameters whenever the current tool response provides
enough evidence.


Current Node (just executed)
----------------------------
{{ current_node }}

The current node may contain:
- id
- goal / node value
- tool name
- tool args
- tool docs
- full tool response
- preconditions
- effects


Current Tool Response (explicit)
--------------------------------
{{ current_tool_response }}

Use this section as the primary source for extracting concrete values.

====================
YOUR TASK
====================

Based on the context above:

1. Summarize what the current tool just did and what its response means.
2. Explain how the current node contributes to the global goal.
3. Describe how this step changes or informs the remaining plan.
4. Highlight important new information, decisions, risks, or follow-up actions.
5. Answer the goal of the current node with explicit values.
6. Inspect the current tool response and identify whether it provides concrete values for any tracked plan parameters.
7. For every tracked parameter that can be filled from the current tool response, return the exact value.
8. If a tracked parameter cannot yet be filled, leave it unresolved and explain what is still missing.

====================
CRITICAL EXTRACTION RULES
====================

- Only use information explicitly present in the provided inputs.
- Do not guess missing values.
- Do not paraphrase concrete values when they are needed later.
- If you say a value was found, you MUST return the exact value in "parameter_updates".
- Do NOT say "retrieved" or "known" for a tracked parameter unless you also provide the exact concrete value.
- Prefer exact strings from the tool response over inferred descriptions.
- Prefer values from the explicit "Current Tool Response" section whenever available.
- If multiple candidate values appear, explain the ambiguity and do not choose unless the evidence clearly supports one.
- A parameter should only be updated when the value is supported by the current tool response.
- If the current tool response is an error, still extract any useful values if they are explicitly present.
- A future tool argument is not considered resolved unless its exact value is explicitly returned.
- Every parameter update MUST include the target_node_id of the node whose tool_args should be updated.

====================
OUTPUT FORMAT
====================

Return ONLY valid JSON as a dictionary with exactly these seven properties:

{
  "current_node_id": string,
  "has_error": boolean,
  "effects_achieved": boolean,
  "missing_effects": [string],
  "summary": string,
  "parameter_updates": [
    {
      "binding_key": string,
      "target_node_id": string,
      "tool_name": string,
      "tool_args": object,
      "evidence": string
    }
  ],
  "unresolved_parameters": [
    {
      "binding_key": string,
      "target_node_id": string,
      "tool_name": string,
      "tool_args": object,
      "missing_reason": string
    }
  ]
}

Rules for "current_node_id":
- Set it to the id of the Current Node that just executed.

Rules for "has_error":
- Set to true when the current tool response indicates an error or failure.
- Set to false otherwise.

Rules for "effects_achieved":
- Set to true only if the current node's intended effects were actually achieved.
- Set to false when the tool ran but did not satisfy the node effects.

Rules for "missing_effects":
- Provide explicit unmet effects when "effects_achieved" is false.
- Use concise strings that map to the current node's declared effects.
- Return [] when all effects were achieved.

Rules for "summary":
- Use plain text.
- Include these sections in order:
  1. Summary of Current Tool
  2. Relation to Global Goal
  3. Impact on Plan / Next Nodes
  4. Key Insights and Follow-ups
  5. Answered Current Goal
- In "Answered Current Goal", provide exact explicit values whenever available.
- If explicit values are missing, clearly state what is missing.

Rules for "parameter_updates":
- Include one entry for each tracked parameter that can be filled from the current tool response.
- "tool_args" must be a dictionary of argument names to exact extracted values.
- Example: {"id": "19ee7a94-867b-808c-beb3-c1dd24c97a25"}
- "evidence" must briefly quote or describe where the value came from.
- "target_node_id" must be copied from the corresponding tracked parameter entry.
- "target_node_id" identifies the future node whose tool_args should be patched with the extracted value.
- If more than one future node can use the same value, return one update per target node.

Rules for "unresolved_parameters":
- Include tracked parameters that remain unresolved after inspecting the current tool response.
- Explain briefly why they could not be filled.
- "target_node_id" must be copied from the corresponding tracked parameter entry.
- "tool_args" must be an object containing unresolved argument names with null or unresolved placeholders.
- Example: {"id": null}

Rules for "current_node_id":
- Always set this to the node id of the tool call that just executed.
- This id must refer to the current observation source, not a future node.

Do not return markdown code fences.
"""