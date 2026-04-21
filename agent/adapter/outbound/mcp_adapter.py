# agent/adapter/outbound/mcp_adapter.py
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import OAuthClientMetadata

from agent.application.ports.outbound.tool_interface import Tools
from agent.adapter.outbound.mcp_oauth_flow import wait_for_oauth_callback

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpEndpointConfig:
    id: str
    transport: str  # "stdio" | "streamable-http"
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    auth: dict[str, Any] | None = None


@dataclass
class _RegisteredTool:
    namespaced_name: str
    server_id: str
    mcp_name: str
    description: str | None
    input_schema: dict[str, Any]
    session: ClientSession


class MCPAdapter(Tools):
    def __init__(self, endpoints: list[McpEndpointConfig], token_storage: TokenStorage | None = None):
        self._endpoints = endpoints
        self._token_storage = token_storage

        self._stack: AsyncExitStack | None = None
        self._tools: dict[str, _RegisteredTool] = {}

        self._pending_oauth_urls: dict[str, str] = {}


    async def connect(self) -> None:
        if self._stack is not None:
            return  # already connected

        self._stack = AsyncExitStack()
        self._tools.clear()

        # Tune these as you like
        init_timeout_s = 60.0
        list_tools_timeout_s = 30.0

        oauth_last = sorted(
            self._endpoints,
            key=lambda e: 1 if (e.auth and e.auth.get("type") == "oauth") else 0
        )

        for endpoint in oauth_last:
            try:
                session = await self._open_session(endpoint, init_timeout_s=init_timeout_s)

                tools_res = await asyncio.wait_for(session.list_tools(), timeout=list_tools_timeout_s)
                for tool in tools_res.tools:
                    namespaced = f"{endpoint.id}.{tool.name}"
                    self._tools[namespaced] = _RegisteredTool(
                        namespaced_name=namespaced,
                        server_id=endpoint.id,
                        mcp_name=tool.name,
                        description=tool.description,
                        input_schema=tool.inputSchema,
                        session=session,
                    )

                logger.info("MCP endpoint '%s' loaded %d tools", endpoint.id, len(tools_res.tools))

            except Exception:
                logger.exception("MCP endpoint '%s' failed to connect/list tools", endpoint.id)
                # continue connecting other endpoints instead of failing the whole agent
                continue

    async def disconnect(self) -> None:
        self._tools.clear()
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None

    async def get_available_tools(self):
        return sorted(self._tools.keys())

    async def get_tools_json(self):
        payload = [
            {"name": rt.namespaced_name, "description": rt.description, "input_schema": rt.input_schema,  "server_id": rt.server_id, "mcp_name": rt.mcp_name}
            for rt in self._tools.values()
        ]
        # TODO: remove later
        # notion_search_spec = next((tool for tool in payload if tool["name"] == "Notion.notion-search"), None)
        # if notion_search_spec is not None:
        #     logger.info("MCP tool spec for LLM: %s", json.dumps(notion_search_spec, ensure_ascii=False))
        return json.dumps(payload, ensure_ascii=False)

    def get_pending_oauth_urls(self):
        return dict(self._pending_oauth_urls)

    def get_tool_spec(self, tool_name: str):
        rt = self._tools[tool_name]
        spec = {
            "name": rt.namespaced_name,
            "description": rt.description,
            "input_schema": rt.input_schema,
            "server_id": rt.server_id,
            "mcp_name": rt.mcp_name,
        }
        return spec

    async def execute_tool(self, fn_name, fn_args):
        rt = self._tools[fn_name]
        result = await rt.session.call_tool(rt.mcp_name, arguments=fn_args)

        structured = getattr(result, "structured_content", None)
        texts: list[str] = []
        for c in result.content:
            txt = getattr(c, "text", None)
            if txt is not None:
                texts.append(txt)

        return {
            "is_error": getattr(result, "isError", False),
            "structured": structured,
            "text": "\n".join(texts) if texts else None,
            "raw": result,
        }

    async def _open_session(self, endpoint: McpEndpointConfig, *, init_timeout_s: float) -> ClientSession:
        if self._stack is None:
            raise RuntimeError("Adapter not initialized (no exit stack). Call connect() first.")

        if endpoint.transport == "stdio":
            params = StdioServerParameters(
                command=endpoint.command,
                args=endpoint.args or [],
                env=endpoint.env or {},
            )

            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=init_timeout_s)
            return session

        if endpoint.transport == "streamable-http":
            if not endpoint.url:
                raise ValueError(f"Endpoint '{endpoint.id}' missing url")

            http_client = await self._build_http_client(endpoint)
            # ensure http_client is closed
            await self._stack.enter_async_context(http_client)

            read, write, _ = await self._stack.enter_async_context(
                streamable_http_client(endpoint.url.rstrip("/"), http_client=http_client)
            )
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=init_timeout_s)
            return session

        raise ValueError(f"Unknown transport: {endpoint.transport}")

    async def _build_http_client(self, endpoint: McpEndpointConfig) -> httpx.AsyncClient:
        # Some MCP servers are picky about Accept; safe default:
        base_headers = {"Accept": "application/json, text/event-stream"}

        if not endpoint.auth:
            return httpx.AsyncClient(headers=base_headers, follow_redirects=True)

        auth_type = endpoint.auth.get("type")

        if auth_type == "oauth":
            if self._token_storage is None:
                raise RuntimeError("OAuth configured but no TokenStorage provided")

            # Expect your config.json to contain these fields (example below)
            server_url = endpoint.auth["server_url"]
            client_metadata = OAuthClientMetadata(**endpoint.auth["client_metadata"])

            async def _redirect_handler(auth_url: str) -> None:
                # You can log + let the user open it in browser
                self._pending_oauth_urls[endpoint.id] = auth_url
                logger.warning("OAuth required for %s. Open in browser: %s", endpoint.id, auth_url)

            async def _callback_handler() -> tuple[str, str | None]:
                # waits until your /mcp/oauth/callback endpoint enqueues (code,state)
                code, state = await wait_for_oauth_callback(timeout=600.0)
                return code, state

            oauth = OAuthClientProvider(
                server_url=server_url,
                client_metadata=client_metadata,
                storage=self._token_storage,
                redirect_handler=_redirect_handler,
                callback_handler=_callback_handler,
            )
            return httpx.AsyncClient(headers=base_headers, auth=oauth, follow_redirects=True)

        if auth_type == "bearer":
            token = endpoint.auth["token"]
            return httpx.AsyncClient(
                headers={**base_headers, "Authorization": f"Bearer {token}"},
                follow_redirects=True,
            )

        raise ValueError(f"Unknown auth type: {auth_type}")
