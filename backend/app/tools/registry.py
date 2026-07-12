import logging
from typing import Dict, List
from app.tools.base_tool import BaseTool
from app.tools.exceptions import ToolRegistryError

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Singleton registry that stores and manages registered Tool instances.
    Provides methods for dynamic retrieval and discovery.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, tool: BaseTool) -> None:
        """Register a new tool instance in the registry, preventing duplicate keys."""
        name = tool.metadata.name
        if name in self._tools:
            raise ToolRegistryError(f"Tool with name '{name}' is already registered.")
        
        self._tools[name] = tool
        logger.info(f"Successfully registered tool: {name} v{tool.metadata.version}")

    def unregister(self, name: str) -> None:
        """Unregister a tool instance from the registry."""
        if name not in self._tools:
            raise ToolRegistryError(f"Tool with name '{name}' not found in registry.")
        del self._tools[name]
        logger.info(f"Successfully unregistered tool: {name}")

    def get(self, name: str) -> BaseTool:
        """Retrieve a registered tool instance by name."""
        if name not in self._tools:
            raise ToolRegistryError(f"Tool with name '{name}' is not registered.")
        return self._tools[name]

    def list(self) -> List[BaseTool]:
        """List all currently registered tool instances."""
        return list(self._tools.values())

    def exists(self, name: str) -> bool:
        """Check if a tool exists in the registry."""
        return name in self._tools

    def clear(self) -> None:
        """Clear all registered tools (mainly for unit testing)."""
        self._tools.clear()

    def discover_plugins(self) -> None:
        """
        Auto-discovery hook: Scans all subclass modules of BaseTool
        and registers their default instantiated classes.
        """
        # Auto-discovery registers all subclasses of BaseTool.
        # This scans already-imported tool modules and automatically registers them.
        for subclass in BaseTool.__subclasses__():
            try:
                # Instantiating default tools
                # To prevent instantiation errors if a subclass constructor requires args,
                # we handle it gracefully here.
                instance = subclass()
                self.register(instance)
            except Exception as e:
                logger.debug(f"Skipping auto-registration for subclass {subclass.__name__}: {e}")


# Global Singleton Registry Instance
tool_registry = ToolRegistry()
