from typing import Any


def render_prompt(agent_session: Any, template: str, context: dict[str, Any]) -> str:
    renderer = getattr(agent_session, "template_renderer", None)
    if renderer is None:
        raise RuntimeError("Missing 'template_renderer' on agent session")
    return renderer.render(template=template, context=context)