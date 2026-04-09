# agent/adapter/inbound/http/api.py
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from agent.adapter.outbound.mcp_oauth_flow import enqueue_oauth_callback
from agent.domain.agent import Agent
from agent.domain.react import loop_run_cycle
from agent.domain.context import Context, Node
from agent.adapter.inbound.http.dependencies import (
    get_tools,
    get_llm,
    get_memory,
    get_planner,
    get_template_renderer,
)
from agent.adapter.serialization.context import context_to_dict

router = APIRouter()
oauth_router = APIRouter(tags=["oauth"])


class PromptRequest(BaseModel):
    prompt: str


class AgentResponse(BaseModel):
    context: Optional[dict]


class ToolSpecResponse(BaseModel):
    name: str
    description: Optional[str]
    input_schema: dict
    server_id: str
    mcp_name: str


@oauth_router.get("/mcp/oauth/callback", include_in_schema=False)
async def mcp_oauth_callback(
    code: str = Query(..., description="Authorization code"),
    state: Optional[str] = Query(None, description="Opaque state"),
):
    await enqueue_oauth_callback(code, state)
    return PlainTextResponse("Auth received. You can close this tab.")

@oauth_router.get("/mcp/oauth/pending")
async def pending_oauth(tools=Depends(get_tools)):
    # works even while MCP connect is waiting
    return {"pending": tools.get_pending_oauth_urls()}


@router.post("/agent", response_model=AgentResponse)
async def call_agent(
    req: PromptRequest,
    request: Request,
    tools=Depends(get_tools),
    llm=Depends(get_llm),
    memory=Depends(get_memory),
    planner=Depends(get_planner),
    template_renderer=Depends(get_template_renderer),
):
    if not getattr(request.app.state, "mcp_ready", False):
        raise HTTPException(status_code=503, detail="MCP not ready yet")

    agent_session = Agent(
        max_steps=3,
        tools=tools,
        llm=llm,
        memory=memory,
        planner=planner,
        template_renderer=template_renderer,
    )

    root_node = Node(value=req.prompt)
    agent_session.context = Context(roots=[root_node])
    agent_session.context.rebuild_indexes()
    agent_session.global_goal_node = root_node

    await loop_run_cycle(agent_session=agent_session)
    
    return AgentResponse(context=context_to_dict(agent_session.context))


@router.get("/tools/{tool_name}", response_model=ToolSpecResponse)
async def get_tool_details(tool_name: str, request: Request):
    if not getattr(request.app.state, "mcp_ready", False):
        raise HTTPException(status_code=503, detail="MCP not ready yet")

    try:
        spec = get_tools(request).get_tool_spec(tool_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found") from exc

    return ToolSpecResponse(**spec)


@router.get("/tools")
async def list_tools(request: Request):
    if not getattr(request.app.state, "mcp_ready", False):
        raise HTTPException(status_code=503, detail="MCP not ready yet")

    tool_names = await get_tools(request).get_available_tools()
    return {"tools": tool_names}
