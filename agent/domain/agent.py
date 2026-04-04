from typing import List, Optional
from uuid import uuid4

from agent.domain.context import Node, Context
from agent.application.ports.outbound.llm_interface import LLM
from agent.application.ports.outbound.tool_interface import Tools
from agent.application.ports.outbound.memory_interface import Memory


class Agent:
    id: uuid4 = uuid4()
    context: Optional[Context]
    memory_context: Optional[Context]
    active_node: Optional[Node]
    global_goal_node: Optional[Node]
    global_goal_answer: str
    max_steps: int
    step_counter: int = 0
    termination: bool = False

    tools: Tools
    llm: LLM
    memory: Memory

    def __init__(self, max_steps: int, llm: LLM, tools: Tools, memory: Memory):
        self.max_steps = max_steps
        self.tools = tools
        self.llm = llm
        self.memory = memory
        self.context = None
        self.active_node = None
        self.global_goal_answer = None
        self.memory_context = None