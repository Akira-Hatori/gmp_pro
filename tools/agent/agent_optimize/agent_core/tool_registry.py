from dataclasses import dataclass
from typing import Any, Callable, Dict, List


ToolHandler = Callable[[Dict[str, Any]], str]


@dataclass
class RegisteredTool:
    schema: Dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, RegisteredTool] = {}

    def register(self, name: str, schema: Dict[str, Any], handler: ToolHandler) -> None:
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = RegisteredTool(schema=schema, handler=handler)

    def schemas(self) -> List[Dict[str, Any]]:
        return [tool.schema for tool in self._tools.values()]

    def run(self, name: str, arguments: Dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(self._tools.keys()) or "none"
            return f"Error: unknown tool {name}. Available tools: {available}"
        return tool.handler(arguments)
