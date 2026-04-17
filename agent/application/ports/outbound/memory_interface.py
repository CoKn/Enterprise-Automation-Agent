from abc import ABC, abstractmethod

from agent.domain.context import Context


class Memory(ABC):
    
    @abstractmethod
    def save(self, context: Context, memory_type: str = "episodic"):
        ...

    @abstractmethod
    def query(self, goal: str, filter: dict | None = None, memory_type: str | None = None):
        ...