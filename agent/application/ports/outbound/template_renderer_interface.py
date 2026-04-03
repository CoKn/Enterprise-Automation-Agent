from abc import ABC, abstractmethod
from typing import Any


class TemplateRenderer(ABC):
    @abstractmethod
    def render(self, template: str, context: dict[str, Any]) -> str:
        ...
