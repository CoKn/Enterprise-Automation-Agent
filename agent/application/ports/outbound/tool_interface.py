# agent/ports/outbound/tool_interface.py
from abc import ABC, abstractmethod

class Tools(ABC):

    @abstractmethod
    async def connect(self):
        ...

    @abstractmethod
    async def disconnect(self):
        ...

    @abstractmethod
    async def get_available_tools(self):
        ...

    @abstractmethod
    async def get_tools_json(self):
        ...

    @abstractmethod
    def get_tool_spec(self, tool_name: str):
        ...

    @abstractmethod
    async def execute_tool(self, fn_name, fn_args):
        ...