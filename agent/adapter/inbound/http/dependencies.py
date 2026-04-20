# agent/adapter/inbound/http/dependencies.py
from fastapi import Request

def get_container(request: Request):
    return request.app.state.container

def get_tools(request: Request):
    return request.app.state.container.tools

def get_llm(request: Request):
    return request.app.state.container.llm

def get_memory(request: Request):
    return request.app.state.container.memory

def get_analytics(request: Request):
    return request.app.state.container.analytics

def get_planner(request: Request):
    return request.app.state.container.planner

def get_template_renderer(request: Request):
    return request.app.state.container.template_renderer

def get_context_serializer(request: Request):
    return request.app.state.container.context_serializer