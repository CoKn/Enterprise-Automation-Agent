from abc import abstractmethod, ABC
from typing import Any

class LLM(ABC):

    @abstractmethod
    def call(self, prompt, system_prompt, json_mode: bool = False) -> dict[str, Any]:
        ...