from abc import ABC, abstractmethod
from datetime import datetime


class AnalyticsDB(ABC):
    @abstractmethod
    def save_run_start(
        self,
        run_id: str,
        initial_prompt: str,
        global_goal: str,
        started_at: datetime,
    ) -> None:
        ...

    @abstractmethod
    def save_call(
        self,
        run_id: str,
        phase: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        created_at: datetime,
    ) -> None:
        ...

    @abstractmethod
    def save_run_finish(
        self,
        run_id: str,
        finished_at: datetime,
        latency_ms: int,
        total_prompt_tokens: int,
        total_completion_tokens: int,
        total_tokens: int,
        total_nodes: int,
        cached_node_count: int,
        new_node_count: int,
        status: str = "completed",
    ) -> None:
        ...

    @abstractmethod
    def mark_goal_achieved(self, run_id: str, goal_achieved: bool = True) -> None:
        ...
