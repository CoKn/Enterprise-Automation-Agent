# plan of the react loop

from agent.domain.agent import Agent
from agent.domain.context import NodeType, NodeStatus
from agent.application.usecases.prompt_rendering import render_prompt

from agent.domain.prompts.react.parameter_generation import parameter_generation_prompt

from agent.logger import get_logger

import json


logger = get_logger(__name__)


async def plan(agent_session: Agent):
    if not agent_session.active_node:
        return
    

    # retrieve plan or context (episodic memory) or semantic memory or None
    filter = {"collection": "nodes_value", "n_results": 1, "max_distance": 0.2}
    existing_plan = agent_session.memory.query(
        agent_session.active_node.value,
        filter=filter,
        memory_type="procedural",
    )
    if existing_plan:
        agent_session.context = existing_plan
        agent_session.global_goal_node = existing_plan.get_root()
        root = agent_session.global_goal_node
        
        # Try to get the next executable node
        next_executable = existing_plan.next_node(root)
        
        if next_executable:
            # Found a next actionable node; use it
            agent_session.active_node = next_executable
            logger.info("Reusing cached plan for goal '%s'", agent_session.active_node.value)
            serialized_context = agent_session.planner.serializer.serialize_context(agent_session.context)
            logger.info("%s:\n%s", "Context Tree", json.dumps(serialized_context, indent=2, default=str))
            return
        elif root.node_type == NodeType.fully_planned:
            # Root is fully planned and ready to execute
            agent_session.active_node = root
            logger.info("Reusing cached plan for goal root '%s'", root.value)
            serialized_context = agent_session.planner.serializer.serialize_context(agent_session.context)
            logger.info("%s:\n%s", "Context Tree", json.dumps(serialized_context, indent=2, default=str))
            return
        elif root.node_type == NodeType.parcially_planned:
            # Root is partially planned; continue to parameter generation
            agent_session.active_node = root
            logger.info("Reusing cached plan (partially planned) for goal root '%s'", root.value)
            # Fall through to parameter generation below
        else:
            # Root is abstract; fall through to planning
            agent_session.active_node = root
            logger.info("Reusing cached plan (abstract) for goal root '%s'", root.value)
    
    # case of failed execution, replan
    if agent_session.active_node.status == NodeStatus.failed and agent_session.active_node.type == NodeType.fully_planned:
        failed_node = agent_session.active_node
        tool_docs = await agent_session.tools.get_tools_json()

        agent_session.context = agent_session.planner.replan(
            context=agent_session.context,
            root=failed_node,
            tool_docs=tool_docs
        )

        new_root = agent_session.context.get_root()
        if not new_root:
            raise RuntimeError("No root available after replanning")

        agent_session.global_goal_node = new_root

        # Continue from the repaired failed-node subtree, not from the global root.
        next_after_repair = agent_session.context.next_node(failed_node)
        if next_after_repair is not None:
            agent_session.active_node = next_after_repair
        elif failed_node.node_type != NodeType.abstract:
            agent_session.active_node = failed_node
        else:
            agent_session.active_node = None

        if agent_session.active_node:
            logger.info(
                "Replanned actionable node goal='%s' type=%s",
                agent_session.active_node.value,
                agent_session.active_node.node_type.name,
            )

        return

    # If the current node is still abstract, ask the planner to expand it
    if agent_session.active_node.node_type == NodeType.abstract:
        tool_docs = await agent_session.tools.get_tools_json()

        agent_session.context = agent_session.planner.plan(
            context=agent_session.context,
            root=agent_session.active_node,
            tool_docs=tool_docs,
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
        
        llm_result = agent_session.llm.call(prompt=parameter_generation_prompt_rendered, json_mode=True)

        if llm_result.get("error"):
            raise RuntimeError(llm_result["error"])

        logger.info(
            "LLM usage phase=parameter_generation prompt_tokens=%s completion_tokens=%s total_tokens=%s",
            llm_result.get("prompt_tokens", 0),
            llm_result.get("completion_tokens", 0),
            llm_result.get("total_tokens", 0),
        )

        resp = llm_result.get("response") or ""

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