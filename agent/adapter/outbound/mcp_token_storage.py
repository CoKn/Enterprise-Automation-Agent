# agent/adapter/outbound/mcp_token_storage.py
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthToken, OAuthClientInformationFull


def _dump_model(obj: Any) -> Any:
    """Serialize pydantic-ish models into JSON-serializable python structures."""
    if obj is None:
        return None

    # pydantic v2
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")

    # pydantic v1
    if hasattr(obj, "json"):
        # obj.json() converts AnyUrl -> string, etc.
        return json.loads(obj.json())

    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            # fallback through JSON
            return json.loads(obj.json())

    return obj



def _load_model(cls: Any, data: Any) -> Any:
    """Deserialize pydantic-ish models safely."""
    if data is None:
        return None
    if hasattr(cls, "model_validate"):  # pydantic v2
        return cls.model_validate(data)
    if hasattr(cls, "parse_obj"):  # pydantic v1
        return cls.parse_obj(data)
    return cls(**data)


@dataclass
class FileTokenStorage(TokenStorage):
    """
    Simple JSON file-backed TokenStorage.

    Notes:
    - Works well for a single-process FastAPI/Uvicorn setup.
    - If you run multiple workers/processes, use a real lock or per-worker storage.
    """
    path: Path

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def get_tokens(self) -> Optional[OAuthToken]:
        async with self._lock:
            data = self._read()
            return _load_model(OAuthToken, data.get("tokens"))

    async def set_tokens(self, tokens: OAuthToken) -> None:
        async with self._lock:
            data = self._read()
            data["tokens"] = _dump_model(tokens)
            self._write(data)

    async def get_client_info(self) -> Optional[OAuthClientInformationFull]:
        async with self._lock:
            data = self._read()
            return _load_model(OAuthClientInformationFull, data.get("client_info"))

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        async with self._lock:
            data = self._read()
            data["client_info"] = _dump_model(client_info)
            self._write(data)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            # Corrupted file -> behave like empty storage
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
