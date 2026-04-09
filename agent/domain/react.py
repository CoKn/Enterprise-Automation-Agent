# Main react loop

from agent.domain.agent import Agent
from agent.domain.context import NodeType, NodeStatus
from agent.application.usecases.prompt_rendering import render_prompt

from agent.domain.prompts.react.step_observation import step_observation_prompt
from agent.domain.prompts.react.parameter_generation import parameter_generation_prompt

from agent.logger import get_logger

import json


logger = get_logger(__name__)


async def plan(agent_session: Agent):
    if not agent_session.active_node:
        return
    
    # TODO: adjust for new memory structure

    # retrieve plan or context (episodic memory) or semantic memory or None
    # check for old plans
    plan_filter = {"status": "completed"}
    if cached := agent_session.memory.retrieve_plan(
        agent_session.active_node.value,
        # TODO: change or remove
        # memory_filter=plan_filter,
        clear_results=True,
    ):
        agent_session.context = cached
        agent_session.global_goal_node = cached.get_root()
        agent_session.active_node = cached.next_node(agent_session.global_goal_node)
        logger.info("Reusing cached plan for goal '%s'", agent_session.active_node.value)

        logger.info("Plan '%s'", agent_session.context)
        return

    # If the current node is still abstract, ask the planner to expand it.
    if agent_session.active_node.node_type == NodeType.abstract:
        agent_session.context = agent_session.planner.plan(
            context=agent_session.context,
            root=agent_session.active_node
        )

        # update agent session with new context, global goal node and active node
        new_root = agent_session.context.get_root()
        if not new_root:
            raise RuntimeError("No root available")

        agent_session.global_goal_node = new_root
        agent_session.active_node = agent_session.context.next_node(new_root) or None

        if agent_session.active_node:
            logger.info(
                "Planner produced actionable node goal='%s' type=%s",
                agent_session.active_node.value,
                agent_session.active_node.node_type.name,
            )
        else:
            return

    if agent_session.active_node.node_type == NodeType.parcially_planned:

        # build context for parameter generation
        previous_nodes_list = agent_session.context.previous_nodes(agent_session.active_node)
        next_nodes_list = agent_session.context.next_nodes(agent_session.active_node)

        previous_nodes = agent_session.context.represent_nodes(nodes=previous_nodes_list)
        next_nodes = agent_session.context.represent_nodes(nodes=next_nodes_list)
        current_node = agent_session.context.represent_nodes(nodes=[agent_session.active_node])

        tool_spec = agent_session.tools.get_tool_spec(agent_session.active_node.tool_name)

        parameter_generation_prompt_rendered = render_prompt(
            agent_session=agent_session,
            template=parameter_generation_prompt,
            context={
                "global_goal": agent_session.global_goal_node.value,
                "current_node": current_node,
                "tool_spec": tool_spec,
                "history": previous_nodes,
                "future_nodes": next_nodes,
            },
        )
        
        resp = agent_session.llm.call(prompt=parameter_generation_prompt_rendered, json_mode=True)

        try:
            agent_session.active_node.tool_args = json.loads(resp).get("arguments")
            agent_session.active_node.node_type = NodeType.fully_planned
            return
        except json.JSONDecodeError as e:
            agent_session.active_node.node_status = NodeStatus.failed

            # bubble up failure status to parents
            agent_session.context.recompute_statuses()

            # update node status in db 
            agent_session.memory.save(context=agent_session.context)

            raise ValueError(
                "Parameter generation response must be valid JSON"
            ) from e
        
    if agent_session.active_node.type == NodeType.fully_planned:
        return
    

async def act(agent_session: Agent):
    # If planning did not set an active node, there is nothing to do.
    if not agent_session.active_node:
        return
    
    # if the current node is abstract do not try to execute
    if agent_session.active_node.node_type == NodeType.abstract:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)

        raise RuntimeError(
            f"Cannot execute node '{agent_session.active_node.id}' before it is fully planned"
        )
    
    # if the current node is parcially planned do not try to execute
    if agent_session.active_node.node_type == NodeType.parcially_planned:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)

        raise RuntimeError(
            f"Cannot execute node '{agent_session.active_node.id}' before it is fully planned"
        )
    

    # case fully planned:
    tool_name = agent_session.active_node.tool_name
    if not tool_name:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)
        raise ValueError(f"Missing 'tool_name' in active node: {agent_session.active_node}")
    
    tool_args = agent_session.active_node.tool_args or {}

    logger.info(
        "Executing tool %s with args=%s on node=%s",
        tool_name,
        tool_args,
        agent_session.active_node.id,
    )

    try:
        agent_session.active_node.tool_response = await agent_session.tools.execute_tool(
            fn_name=tool_name,
            fn_args=tool_args,
        )
        logger.debug(
            "Tool response for %s on node=%s: %s",
            tool_name,
            agent_session.active_node.id,
            agent_session.active_node.tool_response,
        )
        return
    
    except Exception as e:
        agent_session.active_node.node_status = NodeStatus.failed

        # bubble up failure status to parents
        agent_session.context.recompute_statuses()

        # update node status in db 
        agent_session.memory.save(context=agent_session.context)

        raise RuntimeError(f"Tool execution failed for '{tool_name}': {e}") from e
    

async def observe(agent_session: Agent):

    if not agent_session.active_node:
        return

    # build context for tool response summary
    global_goal = str(agent_session.global_goal_node)
    previous_nodes_list = agent_session.context.previous_nodes(agent_session.active_node)
    next_nodes_list = agent_session.context.next_nodes(agent_session.active_node)

    previous_nodes = agent_session.context.represent_nodes(nodes=previous_nodes_list)
    next_nodes = agent_session.context.represent_nodes(nodes=next_nodes_list)
    current_node = agent_session.context.represent_nodes(nodes=[agent_session.active_node])

    # format
    step_observation_prompt_rendered = render_prompt(
        agent_session=agent_session,
        template=step_observation_prompt,
        context={
            "global_goal": global_goal,
            "previous_nodes": previous_nodes,
            "next_nodes": next_nodes,
            "current_node": current_node,
        },
    )

    agent_session.active_node.tool_response_summary = agent_session.llm.call(prompt=step_observation_prompt_rendered)

    metadata = agent_session.memory.save(context=agent_session.context)
    logger.debug("Persisted context metadata: %s", metadata)
    logger.info(
        "Observation summary node=%s: %s",
        agent_session.active_node.id,
        agent_session.active_node.tool_response_summary,
    )

    # mark active node as complete
    agent_session.active_node.node_status = NodeStatus.success

    # bubble up completion to parents
    agent_session.context.recompute_statuses()

    # update node status in db 
    agent_session.memory.save(context=agent_session.context)

    # set next active node if a next node exists
    if (next_node := agent_session.context.next_node(agent_session.active_node)):
        agent_session.active_node = next_node



async def run_cycle(agent_session: Agent):

    # create plan / pick parameters
    await plan(agent_session)

    # execute tool
    await act(agent_session)

    # create summary of tool response
    await observe(agent_session)


async def loop_run_cycle(agent_session: Agent):
    # loop react cycle 
    while not agent_session.termination:

        # terminate if max steps are reached
        if agent_session.max_steps == agent_session.step_counter:
            return
        
        if not agent_session.global_goal_node:
            return
        
        if not agent_session.active_node:
            agent_session.active_node = agent_session.global_goal_node

        await run_cycle(agent_session=agent_session)

        agent_session.step_counter += 1