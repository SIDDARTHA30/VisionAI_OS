import logging
from app.tools.registry import tool_registry
from app.tools.base_tool import BaseTool
from app.tools.context import ToolContext
from app.tools.result import ToolResult
from app.tools.enums import ToolStatus, ToolCategory, PermissionLevel, ToolCapability
from app.tools.metadata import ToolMetadata
from app.tools.schemas import ToolHealth
from app.tools.factory import ToolFactory
from app.tools.manager import ToolManager

# Import concrete tool subclasses to ensure they are loaded into subclass registry list
from app.tools.browser.browser_tool import BrowserTool
from app.tools.python.python_tool import PythonTool
from app.tools.filesystem.file_tool import FileTool
from app.tools.search.search_tool import SearchTool
from app.tools.utility.calculator_tool import CalculatorTool

logger = logging.getLogger(__name__)

# Trigger auto-discovery of subclasses on initialization
try:
    tool_registry.discover_plugins()
    logger.info(f"Auto-discovery successfully registered {len(tool_registry.list())} tools.")
except Exception as e:
    logger.error(f"Failed to auto-discover tool plugins: {e}")

__all__ = [
    "BaseTool",
    "ToolContext",
    "ToolResult",
    "ToolStatus",
    "ToolCategory",
    "PermissionLevel",
    "ToolCapability",
    "ToolMetadata",
    "ToolHealth",
    "tool_registry",
    "ToolFactory",
    "ToolManager",
    "BrowserTool",
    "PythonTool",
    "FileTool",
    "SearchTool",
    "CalculatorTool"
]
