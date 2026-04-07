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