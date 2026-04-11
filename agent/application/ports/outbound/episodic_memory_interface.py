from abc import ABC, abstractmethod


class EpisodicMemoryPort(ABC):
    
    @abstractmethod
    def find_matching_episodes(self, 
                               goal: str, 
                               precon: list[dict]=None, 
                               effects: list[dict]=None,
                               threshold: float | None=None,
                               limit: int = 3):
        ... 
