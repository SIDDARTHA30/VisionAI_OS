import logging
from typing import Dict, List
from app.tools.base_tool import BaseTool

logger = logging.getLogger("app.tools.registry")


class ToolRegistry:
    """Architectural placeholder for dynamic tool registration & resolution."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name.lower()] = tool
        logger.info(f"Registered plugin tool: {tool.name} (v{tool.version})")

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name.lower())
        if not tool:
            raise KeyError(f"Plugin Tool '{name}' is not registered.")
        return tool

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())


# Global Registry Instance
tool_registry = ToolRegistry()
