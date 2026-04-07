# agent/bootstrap.py
from dataclasses import dataclass
from pathlib import Path
import json
import os

from agent.adapter.outbound.openai_adapter import OpenAIAdapter
from agent.adapter.outbound.mcp_adapter import MCPAdapter, McpEndpointConfig
from agent.adapter.outbound.mcp_token_storage import FileTokenStorage
from agent.utility import check_if_folder_exists


@dataclass
class AppContainer:
    memory: ...
    llm: OpenAIAdapter
    tools: MCPAdapter

    async def start(self):
        await self.tools.connect()

    async def stop(self):
        await self.tools.disconnect()


def build_container(base_dir: Path) -> AppContainer:
    # TODO: add memory
    db_path = check_if_folder_exists(base_dir / "db")
    memory = ... # memory client

    llm = OpenAIAdapter(
        api_key=os.getenv("OPENAI_API_KEY"),
        deployment_name=os.getenv("LLM_MODEL"),
    )

    config_path = base_dir / "agent" / "config.json"
    if not config_path.exists():
        raise ValueError("config.json does not exist")

    raw = config_path.read_text(encoding="utf-8")
    data = json.loads(raw)

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

    return AppContainer(
        memory=memory,
        llm=llm,
        tools=tools,
    )