EXTENSION_PLANNING_PROMPT = """
You extend an existing planning tree without destroying previous progress.

Return ONLY incremental additions for the provided extension root.
Do not re-output completed branches from history.
Do not duplicate previously completed or equivalent leaves.

Use this exact Node schema and enum values:
- type: \"abstract\", \"parcially_planned\", \"fully_planned\"
- status: \"pending\", \"success\", \"failed\"

JSON rules:
- id, parent, next, previous, created_at, tool_response, tool_response_summary = null
- children must always be an array
- abstract => tool_name=null, tool_args=null
- parcially_planned => tool_name!=null, tool_args=null
- fully_planned => tool_name!=null, tool_args!=null

Goal:
- Extend the subtree rooted at the provided extension root.
- Preserve existing progress by proposing only missing next goals.
- Prefer at least one execution-ready next leaf when possible.

Output format (JSON only):
{{
  "root": {{
    "id": null,
    "value": "extension root goal",
    "type": "abstract",
    "tool_name": null,
    "tool_args": null,
    "tool_response": null,
    "tool_response_summary": null,
    "preconditions": [],
    "effects": [],
    "parent": null,
    "next": null,
    "previous": null,
    "status": "pending",
    "created_at": null,
    "children": []
  }}
}}

Available Tools:
{tool_docs}
"""
