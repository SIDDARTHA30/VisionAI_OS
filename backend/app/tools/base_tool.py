from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Awaitable
from app.tools.metadata import ToolMetadata
from app.tools.context import ToolContext
from app.tools.result import ToolResult
from app.tools.schemas import ToolHealth


class BaseTool(ABC):
    """
    Abstract Base Class that all pluggable tools must inherit.
    Ensures complete lifecycle, validation, and metadata compatibility.
    """

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Return static metadata details of the tool."""
        pass

    @abstractmethod
    def validate_permissions(self, context: ToolContext) -> None:
        """Validate if execution context satisfies tool permission levels."""
        pass

    @abstractmethod
    def validate_input(self, arguments: Dict[str, Any]) -> None:
        """Validate if input arguments match Pydantic or custom schema bounds."""
        pass

    @abstractmethod
    def validate_workspace(self, context: ToolContext) -> None:
        """Verify that workspace path directories are safe and isolated."""
        pass

    @abstractmethod
    def validate_dependencies(self) -> None:
        """Verify that any external binaries or dependencies exist."""
        pass

    @abstractmethod
    def validate_environment(self) -> None:
        """Verify environment variables and system settings are valid."""
        pass

    @abstractmethod
    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolContext,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> ToolResult:
        """Main execution block of the tool."""
        pass

    @abstractmethod
    async def cleanup(self, context: ToolContext) -> None:
        """Release session locks, shut down connections or temp files."""
        pass

    @abstractmethod
    async def health_check(self) -> ToolHealth:
        """Return granular status metrics of the tool and dependencies."""
        pass

    # ─── Extensibility Hooks for Future Milestones ────────────────────────────

    async def stream_chunk(self, chunk: Any, context: ToolContext) -> None:
        """Placeholder hook for streaming incremental outputs."""
        pass
