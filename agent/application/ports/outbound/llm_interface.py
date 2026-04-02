from abc import abstractmethod, ABC

class LLM(ABC):

    @abstractmethod
    def call(self, prompt, system_prompt, json_mode: bool = False):
        ...