# agent/main.py
from agent.adapter.inbound.http.api import router, oauth_router
from agent.singletons import tools
from agent.logging import configure_logging, get_logger

import asyncio
from contextlib import asynccontextmanager, suppress

import uvicorn
from fastapi import FastAPI

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mcp_status = "booting"   # booting | ready | error
    app.state.mcp_ready = False
    shutdown_event = asyncio.Event()

    async def mcp_manager():
        try:
            await tools.connect()  # can block waiting for OAuth callback, but HTTP server is already up
            app.state.mcp_status = "ready"
            app.state.mcp_ready = True
            logger.info("MCP connected. %d tools loaded.", len(await tools.get_available_tools()))

            # keep running until shutdown
            await shutdown_event.wait()

        except asyncio.CancelledError:
            # expected on shutdown
            raise
        except Exception:
            app.state.mcp_status = "error"
            app.state.mcp_ready = False
            logger.exception("MCP connect FAILED")
        finally:
            # IMPORTANT: disconnect in the SAME task that did connect()
            with suppress(Exception):
                await tools.disconnect()
            app.state.mcp_ready = False

    app.state.mcp_task = asyncio.create_task(mcp_manager())

    # do not block startup
    yield

    shutdown_event.set()

    task = getattr(app.state, "mcp_task", None)
    if task and not task.done():
        task.cancel()
        with suppress(Exception):
            await task


app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/v1", tags=["agent"])
app.include_router(oauth_router, tags=["oauth"])

if __name__ == "__main__":
    uvicorn.run("agent.main:app", host="0.0.0.0", port=8090, reload=False)
