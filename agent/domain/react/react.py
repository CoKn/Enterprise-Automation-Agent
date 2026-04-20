# Main react loop

from agent.domain.agent import Agent
from agent.domain.react.plan import plan
from agent.domain.react.act import act
from agent.domain.react.observe import observe
from agent.domain.react.reflect import reflect
from agent.logger import get_logger


logger = get_logger(__name__)



async def run_cycle(agent_session: Agent):

    # create plan / pick parameters
    await plan(agent_session)

    # execute tool
    await act(agent_session)

    # create summary of tool response
    await observe(agent_session)


async def loop_run_cycle(agent_session: Agent):
    # loop react cycle 
    run_error = False
    reflect_error = False
    try:
        while not agent_session.termination:

            # terminate if max steps are reached
            if agent_session.max_steps == agent_session.step_counter:
                break
            
            if not agent_session.global_goal_node:
                break
            
            if not agent_session.active_node:
                agent_session.active_node = agent_session.global_goal_node

            await run_cycle(agent_session=agent_session)

            agent_session.step_counter += 1
    except Exception:
        run_error = True
        raise
    finally:
        if agent_session.global_goal_node:
            try:
                await reflect(agent_session=agent_session)
            except Exception:
                reflect_error = True
                raise
            finally:
                agent_session.finish_run(status="failed" if (run_error or reflect_error) else "completed")