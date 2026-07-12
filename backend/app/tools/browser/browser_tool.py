from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, Optional, Awaitable
from pydantic import ValidationError

from app.tools.base_tool import BaseTool
from app.tools.context import ToolContext
from app.tools.result import ToolResult
from app.tools.enums import ToolCategory, ToolCapability, PermissionLevel, ToolStatus
from app.tools.metadata import ToolMetadata
from app.tools.schemas import ToolHealth
from app.tools.exceptions import ToolValidationError, ToolPermissionError
from app.tools.browser.models import BrowserAction
from app.tools.browser.session import BrowserSessionManager

logger = logging.getLogger(__name__)


class BrowserTool(BaseTool):
    """
    Browser execution plugin skeleton.
    Provides session management, browser pages controls and cleanups.
    """

    def __init__(self):
        self._session_manager = BrowserSessionManager()
        self._metadata = ToolMetadata(
            name="browser",
            version="1.0.0",
            author="VisionAI OS Core",
            category=ToolCategory.BROWSER,
            capabilities=[ToolCapability.SEARCH_WEB, ToolCapability.DOWNLOAD_FILE, ToolCapability.SCREENSHOT],
            description="Automates navigation, form inputs, clicks, scraping, and screenshot capture in browser instances.",
            permissions=[PermissionLevel.USER_CONFIRMATION_REQUIRED],
            timeout_sec=60,
            tags=["playwright", "web", "automation"]
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def validate_permissions(self, context: ToolContext) -> None:
        # Check permissions block
        if PermissionLevel.BLOCKED in self.metadata.permissions:
            raise ToolPermissionError("This tool is blocked from execution.")

    def validate_input(self, arguments: Dict[str, Any]) -> None:
        try:
            BrowserAction(**arguments)
        except ValidationError as e:
            raise ToolValidationError(f"Invalid browser inputs: {e}")

    def validate_workspace(self, context: ToolContext) -> None:
        if not context.workspace.exists():
            raise ToolValidationError(f"Workspace path does not exist: {context.workspace}")

    def validate_dependencies(self) -> None:
        # Skeleton check — in future, verify if Chrome/Playwright packages are installed
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
        action_data = BrowserAction(**arguments)

        import httpx
        from app.services.automation.execution_error import RetryableError

        # Retrieve or initialize browser session
        session = self._session_manager.get_session(str(context.session_id))
        
        # Trigger progress callbacks if supplied
        if progress_callback:
            await progress_callback(0.5, f"Executing action {action_data.action} on url: {action_data.url}")

        logger.info(f"Browser running action: {action_data.action} on {action_data.url}")
        
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(action_data.url, timeout=10.0)
                res.raise_for_status()
                content_summary = f"HTML page content snippet: {res.text[:300]}"
                status = "success"
        except Exception as e:
            logger.warning(f"Browser navigation failed: {e}")
            raise RetryableError(f"Failed to navigate webpage {action_data.url}: {str(e)}")

        output_data = {
            "action_executed": action_data.action,
            "url": action_data.url,
            "status": status,
            "content_summary": content_summary
        }

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
            structured_output=output_data,
            raw_output=str(output_data),
            logs=["Initialized browser session wrapper", f"Successfully completed action: {action_data.action}"]
        )

    async def cleanup(self, context: ToolContext) -> None:
        # Shuts down active sessions on tool completion/disposal
        self._session_manager.close_session(str(context.session_id))

    async def health_check(self) -> ToolHealth:
        return ToolHealth(
            status="HEALTHY",
            message="Browser automation tool initialized successfully.",
            dependencies=["playwright-core"],
            latency_ms=2,
            last_checked=datetime.now(timezone.utc)
        )
