import logging
from typing import Any, Dict
from app.tools.registry import tool_registry

logger = logging.getLogger("app.tools.manager")


class ToolManager:
    """Orchestrates validation, execution, and explicit cleanup of registered plugin tools."""

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Executing tool {tool_name} with args: {arguments}")
        tool = tool_registry.get(tool_name)
        
        # Schema validation
        if not tool.validate(arguments):
            raise ValueError(f"Arguments validation failed for tool '{tool_name}'.")

        # Execute without immediate cleanup to allow long-running tool sessions (Playwright, Python workspace, etc.)
        try:
            result = await tool.execute(arguments)
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}")
            raise e

    async def cleanup_tool(self, tool_name: str) -> None:
        """Explicitly cleans up resources allocated for a specific tool session."""
        try:
            tool = tool_registry.get(tool_name)
            logger.info(f"Cleaning up resources for tool: {tool_name}")
            await tool.cleanup()
        except KeyError:
            logger.warning(f"Tool '{tool_name}' not found in registry during cleanup.")
        except Exception as e:
            logger.error(f"Error cleaning up tool '{tool_name}': {e}")
