from agent.domain.agent import Agent
from agent.domain.context import NodeStatus, NodeType, Context
from agent.domain.react.plan import plan, replan, plan_parameters
from agent.domain.react.act import act
from agent.domain.react.observe import observe
from agent.domain.react.reflect import reflect


async def run_cycle(agent_session: Agent):
    node = agent_session.active_node
    if not node:
        return

    # case 1: active node is abstract and needs expantion
    if node.type == NodeType.abstract:
        await plan(agent_session=agent_session)
        return

    
    # case 2: active node is parcially planned and needs parameters filled
    elif node.type == NodeType.parcially_planned:
        await plan_parameters(agent_session=agent_session)
        return


    # case 3: active node is fully planned but the status if failed and need repair
    elif (
        node.type == NodeType.fully_planned and 
        node.status == NodeStatus.failed
    ):
        await replan(agent_session=agent_session)
        return

    # case 4: active node is fully planned and needs execution (act + observe)
    elif node.type == NodeType.fully_planned:
        await act(agent_session=agent_session)
        await observe(agent_session=agent_session)
        return
    
    else:
        raise RuntimeError(f"Unexpected Agent State for context: {agent_session.context}")
    

async def loop_run_cycle(agent_session: Agent) -> Context:
    
    # for agent statistics
    run_error = False
    completed = False

    try:
        if not agent_session.active_node and agent_session.global_goal_node:
            agent_session.active_node = agent_session.global_goal_node

        while True:
            while True:
                # termination condition 1: stop agent if step counter is may runs
                if agent_session.step_counter >= agent_session.max_steps:
                    break

                # termination condition 2: stop agent if goal achived
                if agent_session.global_goal_achived:
                    break

                # termination condition 3: no active goal beacuse plan finished
                if not agent_session.active_node:
                    break

                await run_cycle(agent_session=agent_session)

                agent_session.step_counter += 1

            # run reflection to get answer and determin if goal was achived
            if agent_session.skip_reflection:
                completed = True

                #TODO: Remove this later
                agent_session.analytics.mark_goal_achieved(
                    run_id=agent_session.run_id,
                    goal_achieved=True,
                )
                return agent_session.context

            if await reflect(agent_session=agent_session):
                completed = True
                return agent_session.context
            
            # TODO: remove to integrate replanning
            return agent_session.context

            # reflect says goal is not achieved; stop only if budget is exhausted
            if agent_session.step_counter >= agent_session.max_steps:
                agent_session.termination = True
                return agent_session.context

            root = agent_session.global_goal_node
            if not root:
                agent_session.termination = True
                return agent_session.context

            # keep accumulated progress and ask planner to extend the existing tree
            root.node_status = NodeStatus.pending
            root.node_type = NodeType.abstract

            agent_session.context.rebuild_indexes()
            agent_session.active_node = root
            agent_session.global_goal_achived = False
            agent_session.termination = False

    except Exception:
        run_error = True
        raise

    finally:
        agent_session.finish_run(
            status="completed" if (completed and not run_error) else "failed"
        )
