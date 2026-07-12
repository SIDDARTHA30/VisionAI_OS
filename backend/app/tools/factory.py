import logging
from app.tools.base_tool import BaseTool
from app.tools.registry import tool_registry
from app.tools.exceptions import ToolRegistryError

logger = logging.getLogger(__name__)


class ToolFactory:
    """
    Factory class providing clean abstractions to instantiate and fetch tools.
    Enables orchestrators to create tools dynamically by name.
    """

    @staticmethod
    def create(name: str) -> BaseTool:
        """
        Create (resolve) a registered tool instance by name.
        Raises ToolRegistryError if not found.
        """
        try:
            return tool_registry.get(name)
        except ToolRegistryError as e:
            logger.error(f"ToolFactory failed to resolve tool '{name}': {e}")
            raise
