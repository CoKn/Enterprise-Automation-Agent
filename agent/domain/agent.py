from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from agent.application.ports.outbound.analytics_db_interface import AnalyticsDB
from agent.domain.context import Node, Context
from agent.domain.planner import Planner

from agent.application.ports.outbound.llm_interface import LLM
from agent.application.ports.outbound.tool_interface import Tools
from agent.application.ports.outbound.memory_interface import Memory
from agent.application.ports.outbound.template_renderer_interface import TemplateRenderer


class Agent:
    id: UUID
    context: Optional[Context]
    memory_context: Optional[Context]
    active_node: Optional[Node]
    global_goal_node: Optional[Node]
    global_goal_answer: str
    global_goal_achived: bool = False
    initial_prompt: Optional[str]
    run_started_at: Optional[datetime]
    max_steps: int
    step_counter: int = 0
    termination: bool = False
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    skip_reflection: bool = False

    tools: Tools
    llm: LLM
    memory: Memory
    analytics: Optional[AnalyticsDB]
    planner: Planner
    template_renderer: TemplateRenderer

    def __init__(
        self,
        max_steps: int,
        llm: LLM,
        tools: Tools,
        memory: Memory,
        analytics: Optional[AnalyticsDB],
        planner: Planner,
        template_renderer: TemplateRenderer,
    ):
        self.id = uuid4()
        self.max_steps = max_steps
        self.tools = tools
        self.llm = llm
        self.memory = memory
        self.analytics = analytics
        self.template_renderer = template_renderer
        self.context = None
        self.active_node = None
        self.global_goal_answer = None
        self.initial_prompt = None
        self.run_started_at = None
        self.memory_context = None
        self.planner = planner
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.skip_reflection = False

    @property
    def run_id(self) -> str:
        return str(self.id)

    def update_active_node(self) -> Optional[Node]:
        if not self.context or not self.active_node:
            self.active_node = None
            return None

        next_node_id = self.active_node.next
        if not next_node_id:
            self.active_node = None
            return None

        next_node = self.context.get_node(next_node_id)
        if not next_node:
            self.active_node = None
            return None

        self.active_node = next_node
        return next_node

    def start_run(self, initial_prompt: str) -> None:
        root_node = self.context.get_root() if self.context else None
        if root_node is not None:
            self.initial_prompt = root_node.value
        else:
            self.initial_prompt = initial_prompt

        self.skip_reflection = False

        self.run_started_at = datetime.now()

        if not self.analytics or not self.global_goal_node:
            return

        self.analytics.save_run_start(
            run_id=self.run_id,
            initial_prompt=self.initial_prompt,
            global_goal=self.global_goal_node.value,
            started_at=self.run_started_at,
        )

    def record_llm_usage(self, phase: str, llm_result: dict[str, Any]) -> None:
        prompt_tokens = int(llm_result.get("prompt_tokens") or 0)
        completion_tokens = int(llm_result.get("completion_tokens") or 0)
        total_tokens = int(llm_result.get("total_tokens") or 0)
        model = str(llm_result.get("model") or "unknown")
        provider = str(llm_result.get("provider") or "unknown")

        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_tokens += total_tokens

        if not self.analytics or not self.run_started_at:
            return

        self.analytics.save_call(
            run_id=self.run_id,
            phase=phase,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            created_at=datetime.now(),
        )

    def finish_run(self, status: str = "completed") -> None:
        if not self.analytics or not self.run_started_at:
            return

        finished_at = datetime.now()
        latency_ms = int((finished_at - self.run_started_at).total_seconds() * 1000)

        total_nodes = 0
        cached_node_count = 0
        new_node_count = 0
        if self.context is not None:
            self.context.rebuild_indexes()
            total_nodes = len(self.context.node_index)
            cached_node_count = sum(1 for node in self.context.node_index.values() if node.cached)
            new_node_count = total_nodes - cached_node_count

        self.analytics.save_run_finish(
            run_id=self.run_id,
            finished_at=finished_at,
            latency_ms=latency_ms,
            total_prompt_tokens=self.total_prompt_tokens,
            total_completion_tokens=self.total_completion_tokens,
            total_tokens=self.total_tokens,
            total_nodes=total_nodes,
            cached_node_count=cached_node_count,
            new_node_count=new_node_count,
            status=status,
        )