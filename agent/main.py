# agent/main.py
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI

from agent.bootstrap import build_container
from agent.adapter.inbound.http.api import router, oauth_router
from agent.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mcp_status = "booting"
    app.state.mcp_ready = False

    base_dir = Path(__file__).resolve().parents[1]
    container = build_container(base_dir)
    app.state.container = container

    try:
        await container.start()
        app.state.mcp_status = "ready"
        app.state.mcp_ready = True
        logger.info("MCP connected")
        yield
    except Exception:
        app.state.mcp_status = "error"
        app.state.mcp_ready = False
        logger.exception("Startup failed")
        raise
    finally:
        await container.stop()
        app.state.mcp_ready = False


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(router, prefix="/v1", tags=["agent"])
    app.include_router(oauth_router, tags=["oauth"])
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("agent.main:app", host="0.0.0.0", port=8090, reload=False)
