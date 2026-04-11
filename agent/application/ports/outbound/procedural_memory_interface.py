from abc import ABC, abstractmethod


class ProceduralMemoryPort(ABC):
    
    @abstractmethod
    def find_matching_plan(self, 
                           goal: str, 
                           precon: list[dict]=None, 
                           effects: list[dict]=None, 
                           threshold: float | None=None):  # None means best match
        ... 
