from abc import ABC, abstractmethod


class SemanticMemoryPort(ABC):
    
    @abstractmethod
    def gather_facts(self,
                     goal: str,
                     spread: int=1,
                     threshold: float | None=None,
                     limit: int = 5) -> list[str]:
        ... 
