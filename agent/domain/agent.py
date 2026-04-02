# agent definition

from uuid import uuid4
from context import Node

class Agent:

    id: uuid4 = uuid4()
    step_counter: int
    max_steps: int
    goal_queue: list[Node]  # all root goals are saves in the goal queue
    active_goal: Node
