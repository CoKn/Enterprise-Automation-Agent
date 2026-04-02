"""Shared primitives for coordinating OAuth flows between the HTTP API and MCP clients."""

from __future__ import annotations

import asyncio
from typing import Optional, Tuple

# Queue used to hand authorization codes from the FastAPI callback endpoint
# to the MCP HTTP client. Each item is a tuple of (code, optional state).
oauth_queue: "asyncio.Queue[tuple[str, Optional[str]]]" = asyncio.Queue()


def queue_size() -> int:
    """Return the number of pending OAuth callbacks waiting to be consumed."""
    return oauth_queue.qsize()


async def enqueue_oauth_callback(code: str, state: Optional[str]) -> None:
    """Push an incoming OAuth callback payload into the shared queue."""
    await oauth_queue.put((code, state))


async def wait_for_oauth_callback(timeout: Optional[float] = None) -> Tuple[str, Optional[str]]:
    """Await the next OAuth callback, optionally enforcing a timeout."""
    if timeout is None:
        return await oauth_queue.get()
    return await asyncio.wait_for(oauth_queue.get(), timeout=timeout)
