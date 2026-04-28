from agent.domain.prompts.planner import (
    planning_prompt, 
    extension_planning_prompt,
    replanning_prompt
)

from agent.domain.prompts.react import (
    parameter_generation,
    reflection_prompt,
    step_observation
)

from agent.application.usecases.prompt_rendering import render_prompt
from agent.domain.agent import Agent

import json

# react prompts
def build_obervation_prompt(agent_session: Agent) -> str:
    node = agent_session.active_node
    previous_nodes_list = agent_session.context.previous_nodes(node)
    next_nodes_list = agent_session.context.next_nodes(node)

    return render_prompt(
        agent_session=agent_session,
        template=step_observation.STEP_OBSERVATION_PROMP,
        context={
            "global_goal": agent_session.global_goal_node.value,
            "previous_nodes": agent_session.context.represent_nodes(nodes=previous_nodes_list),
            "next_nodes": agent_session.context.represent_nodes(nodes=next_nodes_list),
            "current_node": agent_session.context.represent_nodes(nodes=[node]),
            "tracked_parameters": agent_session.context.get_leaf_nodes_tool_args(),
            "current_tool_response": node.tool_response,
        },
    )


def build_reflection_prompt(agent_session: Agent) -> str:
    full_context_tree = agent_session.planner.serializer.serialize_context(agent_session.context)

    return render_prompt(
        agent_session=agent_session,
        template=reflection_prompt.REFLECTION_PROMPT,
        context={
            "global_goal": agent_session.global_goal_node.value,
            "full_context_tree": json.dumps(full_context_tree),
        },
    )


def build_parameter_generation_prompt(agent_session: Agent) -> str:
    previous_nodes_list = agent_session.context.previous_nodes(agent_session.active_node)
    next_nodes_list = agent_session.context.next_nodes(agent_session.active_node)

    previous_nodes = agent_session.context.represent_nodes(nodes=previous_nodes_list)
    next_nodes = agent_session.context.represent_nodes(nodes=next_nodes_list)
    current_node = agent_session.context.represent_nodes(nodes=[agent_session.active_node])

    tool_spec = agent_session.tools.get_tool_spec(agent_session.active_node.tool_name)

    return render_prompt(
        agent_session=agent_session,
        template=parameter_generation.PARAMETER_GENERATION_PROMPT,
        context={
            "global_goal": agent_session.global_goal_node.value,
            "current_node": current_node,
            "tool_spec": tool_spec,
            "history": previous_nodes,
            "future_nodes": next_nodes,
        },
    )


# planner prompts 
def build_planning_prompt(agent_session: Agent) -> str:

    #TODO: check if I really need this serialisaiton here
    context_payload = agent_session.planner.serializer.serialize_context(agent_session.context)

    # Build the complete prompt with instructions + context
    prompt = render_prompt(
        agent_session=agent_session,
        template=planning_prompt.PLANNING_PROMPT,
        context={
            "tool_docs": json.dumps(agent_session.tools, indent=2),
            "goal": agent_session.global_goal_node.value,
            "context": json.dumps(context_payload, indent=2),
        },
    )
    
    return prompt


def build_replanning_prompt(agent_session: Agent) -> str:
    root = agent_session.active_node
    context = agent_session.context
    tool_docs = json.dumps(agent_session.tools, indent=2)

    root_payload = agent_session.planner.serializer.serialize_node(root)
    context_payload = agent_session.planner.serializer.serialize_context(context)

    prompt = render_prompt(
        agent_session=agent_session,
        template=replanning_prompt.REPLANNING_PROMPT,
        context={
            "tool_docs": tool_docs,
            "goal": root.value if root is not None else None,
            "failed_node": json.dumps(root_payload, indent=2),
            "context": json.dumps(context_payload, indent=2),
        },
    )

    return prompt


def build_plan_extention_prompt(agent_session: Agent) -> str:
    root = agent_session.active_node
    context = agent_session.context
    tool_docs = json.dumps(agent_session.tools, indent=2)

    root_payload = agent_session.planner.serializer.serialize_node(root)
    context_payload = agent_session.planner.serializer.serialize_context(context)

    prompt = render_prompt(
        agent_session=agent_session,
        template=extension_planning_prompt.EXTENSION_PLANNING_PROMPT,
        context={
            "tool_docs": tool_docs,
            "goal": root.value if root is not None else None,
            "extension_root": json.dumps(root_payload, indent=2),
            "context": json.dumps(context_payload, indent=2),
        },
    )

    return prompt



