from abc import ABC, abstractmethod

from agent.domain.context import Context


class Memory(ABC):
    
    @abstractmethod
    def save(self, context: Context):
        ...

    @abstractmethod
    def query(self, query: str, filter: dict, n_results: int):
        ...

    @abstractmethod
    def retrieve_plan(goal_text: str, clear_results: bool) -> Context | None:
        ...