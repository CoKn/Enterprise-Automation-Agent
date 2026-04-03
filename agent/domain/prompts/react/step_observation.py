from jinja2 import Environment, StrictUndefined

env = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)


step_observation_prompt = env.from_string("""
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
5. Answer the question of the goal of the current node. Give the explicet values that are being asked.

Follow these guidelines:
- Only use information provided in the inputs; do not invent tools, data, or results.
- If something is missing or unclear, state that explicitly instead of guessing.
- Focus on what is relevant for guiding subsequent planning and tool choices.

====================
OUTPUT FORMAT
====================

Return your answer as plain text using the following structure:

Summary of Current Tool
- ...

Relation to Global Goal
- ...

Impact on Plan / Next Nodes
- ...

Key Insights and Follow-ups
- ...

Answered Question / Goal of the current node. Give the explicet values that are being asked.
...

""")