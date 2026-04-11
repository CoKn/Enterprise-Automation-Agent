from abc import ABC, abstractmethod

from agent.domain.context import Context


class Memory(ABC):
    
    @abstractmethod
    def save(self, context: Context):
        ...

    @abstractmethod
    def query(self, goal: str, filter: dict | None):
        ...