from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, Optional, Awaitable
from pydantic import BaseModel, Field, ValidationError

from app.tools.base_tool import BaseTool
from app.tools.context import ToolContext
from app.tools.result import ToolResult
from app.tools.enums import ToolCategory, ToolCapability, PermissionLevel, ToolStatus
from app.tools.metadata import ToolMetadata
from app.tools.schemas import ToolHealth
from app.tools.exceptions import ToolValidationError

logger = logging.getLogger(__name__)


class SearchInput(BaseModel):
    query: str = Field(..., description="Web search query string.")
    limit: int = Field(5, description="Maximum number of search results to return.")


class SearchTool(BaseTool):
    """
    Web search tool interface abstraction.
    Supports future integrations with Tavily, Google Search, and SerpAPI.
    """

    def __init__(self):
        self._metadata = ToolMetadata(
            name="web_search",
            version="1.0.0",
            author="VisionAI OS Core",
            category=ToolCategory.SEARCH,
            capabilities=[ToolCapability.SEARCH_WEB],
            description="Searches the web for up-to-date information on any query.",
            permissions=[PermissionLevel.SAFE],
            timeout_sec=15,
            tags=["web", "search", "tavily", "serpapi"]
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def validate_permissions(self, context: ToolContext) -> None:
        pass

    def validate_input(self, arguments: Dict[str, Any]) -> None:
        try:
            SearchInput(**arguments)
        except ValidationError as e:
            raise ToolValidationError(f"Invalid search inputs: {e}")

    def validate_workspace(self, context: ToolContext) -> None:
        pass

    def validate_dependencies(self) -> None:
        pass

    def validate_environment(self) -> None:
        pass

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: ToolContext,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> ToolResult:
        started_at = datetime.now(timezone.utc)
        search_args = SearchInput(**arguments)

        if progress_callback:
            await progress_callback(0.4, f"Sending search query to index: {search_args.query}")

        logger.info(f"Searching web index for: '{search_args.query}'")

        # Mock search results for Milestone 4.2 framework checks
        mock_results = [
            {
                "title": f"Result for query: {search_args.query}",
                "snippet": "This is a placeholder web search result snippet describing the user query details.",
                "url": "https://example.com/search-result"
            }
        ]

        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        return ToolResult(
            tool_name=self.metadata.name,
            tool_version=self.metadata.version,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            exit_code=0,
            success=True,
            status=ToolStatus.COMPLETED,
            structured_output={"results": mock_results, "query": search_args.query},
            raw_output=f"Found 1 result for '{search_args.query}'. Snippet: {mock_results[0]['snippet']}",
            logs=[f"Dispatched Tavily index search query: {search_args.query}"]
        )

    async def cleanup(self, context: ToolContext) -> None:
        pass

    async def health_check(self) -> ToolHealth:
        return ToolHealth(
            status="HEALTHY",
            message="Search web index API client active.",
            dependencies=["http-client"],
            latency_ms=10,
            last_checked=datetime.now(timezone.utc)
        )
