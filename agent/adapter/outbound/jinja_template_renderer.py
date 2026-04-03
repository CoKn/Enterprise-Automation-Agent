from typing import Any

from jinja2 import Environment, StrictUndefined

from agent.application.ports.outbound.template_renderer_interface import TemplateRenderer


class JinjaTemplateRenderer(TemplateRenderer):
    def __init__(self) -> None:
        self._env = Environment(
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template: str, context: dict[str, Any]) -> str:
        return self._env.from_string(template).render(**context)
