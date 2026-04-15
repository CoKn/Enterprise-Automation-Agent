# agent/bootstrap.py
from dataclasses import dataclass
from pathlib import Path
import json
import os
from typing import Any
from dotenv import load_dotenv

from agent.adapter.outbound.openai_adapter import OpenAIAdapter
from agent.adapter.outbound.mcp_adapter import MCPAdapter, McpEndpointConfig
from agent.adapter.outbound.mcp_token_storage import FileTokenStorage
from agent.adapter.outbound.planner_json_serializer import ContextJsonSerializer
from agent.adapter.outbound.jinja_template_renderer import JinjaTemplateRenderer
from agent.domain.planner import Planner
from agent.application.ports.outbound.memory_interface import Memory
from agent.adapter.outbound.postgres_adapter import PostgresAdapter
from agent.application.ports.outbound.template_renderer_interface import TemplateRenderer

load_dotenv()

def check_if_folder_exists(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class NullMemory(Memory):
    def save(self, context):
        return None

    def query(self, goal: str, filter: dict | None=None):
        return []

    def retrieve_plan(self, goal_text: str, clear_results: bool) -> Any:
        return None


@dataclass
class AppContainer:
    memory: Memory
    llm: OpenAIAdapter
    tools: MCPAdapter
    context_serializer: ContextJsonSerializer
    planner: Planner
    template_renderer: TemplateRenderer

    async def start(self):
        await self.tools.connect()

    async def stop(self):
        close = getattr(self.memory, "close", None)
        if callable(close):
            close()
        await self.tools.disconnect()


def build_container(base_dir: Path) -> AppContainer:
    db_dir = check_if_folder_exists(base_dir / "db")

    llm = OpenAIAdapter(
        api_key=os.getenv("OPENAI_API_KEY"),
        deployment_name=os.getenv("LLM_MODEL"),
    )

    config_path = base_dir / "agent" / "config.json"
    if not config_path.exists():
        raise ValueError("config.json does not exist")

    raw = config_path.read_text(encoding="utf-8").strip()
    if not raw:
        data = []
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"config.json contains invalid JSON: {config_path}") from exc

    if isinstance(data, list):
        endpoints_data = data
    elif isinstance(data, dict):
        endpoints_data = data.get("mcp_endpoints") or data.get("endpoints") or []
    else:
        raise ValueError("config.json must be a list or object")

    endpoints = [McpEndpointConfig(**endpoint) for endpoint in endpoints_data]

    token_path = check_if_folder_exists(base_dir / "secrets") / "mcp_tokens.json"
    token_storage = FileTokenStorage(token_path)

    tools = MCPAdapter(
        endpoints=endpoints,
        token_storage=token_storage,
    )

    memory_db_path = os.getenv("EPISODIC_MEMORY_DB", str(db_dir / "episodic_memory.sqlite3"))
    
    # memory = NullMemory()
    memory = PostgresAdapter()

    context_serializer = ContextJsonSerializer()
    planner = Planner(llm=llm, serializer=context_serializer)
    template_renderer = JinjaTemplateRenderer()

    return AppContainer(
        memory=memory,
        llm=llm,
        tools=tools,
        context_serializer=context_serializer,
        planner=planner,
        template_renderer=template_renderer,
    )