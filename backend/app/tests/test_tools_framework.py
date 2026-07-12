import asyncio
import logging
import uuid
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.tools.base_tool import BaseTool
from app.tools.context import ToolContext
from app.tools.result import ToolResult
from app.tools.enums import ToolCategory, ToolCapability, PermissionLevel, ToolStatus
from app.tools.metadata import ToolMetadata
from app.tools.schemas import ToolHealth
from app.tools.registry import tool_registry, ToolRegistry
from app.tools.factory import ToolFactory
from app.tools.manager import ToolManager
from app.tools.exceptions import (
    ToolValidationError,
    ToolPermissionError,
    ToolTimeoutError,
    ToolRegistryError
)

# Concrete Tool Skeletons for tests
from app.tools.browser.browser_tool import BrowserTool
from app.tools.python.python_tool import PythonTool
from app.tools.filesystem.file_tool import FileTool
from app.tools.search.search_tool import SearchTool
from app.tools.utility.calculator_tool import CalculatorTool


# ─── Mock Slow Tool for Timeout verification ──────────────────────────────────
class SlowMockTool(BaseTool):
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="slow_mock",
            version="1.0.0",
            author="Test Mock",
            category=ToolCategory.UTILITY,
            capabilities=[ToolCapability.EXECUTE_CODE],
            description="Mock tool that sleeps to verify timeout constraints.",
            permissions=[PermissionLevel.SAFE],
            timeout_sec=1
        )

    def validate_permissions(self, context: ToolContext) -> None:
        pass

    def validate_input(self, arguments: dict) -> None:
        pass

    def validate_workspace(self, context: ToolContext) -> None:
        pass

    def validate_dependencies(self) -> None:
        pass

    def validate_environment(self) -> None:
        pass

    async def execute(self, arguments: dict, context: ToolContext, progress_callback=None) -> ToolResult:
        await asyncio.sleep(2)  # Exceeds the 1-second timeout_sec threshold
        now = datetime.now(timezone.utc)
        return ToolResult(
            tool_name=self.metadata.name,
            tool_version=self.metadata.version,
            started_at=now,
            finished_at=now,
            duration_ms=0,
            exit_code=0,
            success=True,
            status=ToolStatus.COMPLETED
        )

    async def cleanup(self, context: ToolContext) -> None:
        pass

    async def health_check(self) -> ToolHealth:
        return ToolHealth(
            status="HEALTHY",
            latency_ms=1,
            last_checked=datetime.now(timezone.utc)
        )


# ─── Test cases ───────────────────────────────────────────────────────────────

def test_registry_singleton_safety():
    """Verify registry is a singleton and handles duplicate keys."""
    r1 = ToolRegistry()
    r2 = ToolRegistry()
    assert r1 is r2

    # Clear registry for clean test setup
    r1.clear()
    assert len(r1.list()) == 0

    browser = BrowserTool()
    r1.register(browser)
    assert r1.exists("browser")
    assert len(r1.list()) == 1

    with pytest.raises(ToolRegistryError):
        r1.register(browser)  # Duplicate check


def test_registry_lookup_and_removal():
    """Verify unregistering removes tool from lookup dict."""
    r = ToolRegistry()
    r.clear()
    calc = CalculatorTool()
    r.register(calc)
    assert r.get("calculator") is calc

    r.unregister("calculator")
    assert not r.exists("calculator")
    with pytest.raises(ToolRegistryError):
        r.get("calculator")


def test_factory_creation():
    """Verify ToolFactory correctly instantiates and queries the registry."""
    r = ToolRegistry()
    r.clear()
    browser = BrowserTool()
    r.register(browser)

    resolved = ToolFactory.create("browser")
    assert resolved is browser

    with pytest.raises(ToolRegistryError):
        ToolFactory.create("missing_tool")


@pytest.mark.asyncio
async def test_tool_manager_successful_run():
    """Verify the manager controls all validation stages and execution lifecycle."""
    tool = CalculatorTool()
    manager = ToolManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace_path = Path(tmp_dir) / "workspace"
        workspace_path.mkdir()
        temp_path = Path(tmp_dir) / "temp"
        temp_path.mkdir()

        context = ToolContext(
            request_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_id=1,
            correlation_id=uuid.uuid4(),
            logger=logging.getLogger("test_logger"),
            workspace=workspace_path,
            temp_dir=temp_path
        )

        result = await manager.execute_tool(
            tool=tool,
            arguments={"expression": "2 * 5 + 3"},
            context=context
        )

        assert result.success is True
        assert result.status == ToolStatus.COMPLETED
        assert result.structured_output["result"] == 13
        assert len(result.logs) > 0


@pytest.mark.asyncio
async def test_tool_manager_timeout():
    """Verify ToolManager times out executing tasks if slow."""
    tool = SlowMockTool()
    manager = ToolManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace_path = Path(tmp_dir) / "workspace"
        workspace_path.mkdir()
        temp_path = Path(tmp_dir) / "temp"
        temp_path.mkdir()

        context = ToolContext(
            request_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_id=1,
            correlation_id=uuid.uuid4(),
            logger=logging.getLogger("test_logger"),
            workspace=workspace_path,
            temp_dir=temp_path
        )

        result = await manager.execute_tool(
            tool=tool,
            arguments={},
            context=context
        )

        assert result.success is False
        assert result.status == ToolStatus.TIMEOUT
        assert "timed out" in result.error


@pytest.mark.asyncio
async def test_tool_manager_input_validation_failure():
    """Verify validation stages block bad payloads."""
    tool = CalculatorTool()
    manager = ToolManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace_path = Path(tmp_dir) / "workspace"
        workspace_path.mkdir()
        temp_path = Path(tmp_dir) / "temp"
        temp_path.mkdir()

        context = ToolContext(
            request_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_id=1,
            correlation_id=uuid.uuid4(),
            logger=logging.getLogger("test_logger"),
            workspace=workspace_path,
            temp_dir=temp_path
        )

        # Mathematical expression checking validation (allows only safe characters)
        result = await manager.execute_tool(
            tool=tool,
            arguments={"expression": "import os; os.system('echo malicious')"},
            context=context
        )

        assert result.success is False
        assert result.status == ToolStatus.FAILED
        assert "Invalid math expression" in result.error


@pytest.mark.asyncio
async def test_filesystem_path_traversal_blocking():
    """Verify file tools reject path traversals."""
    tool = FileTool()
    manager = ToolManager()

    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace_path = Path(tmp_dir) / "workspace"
        workspace_path.mkdir()
        temp_path = Path(tmp_dir) / "temp"
        temp_path.mkdir()

        context = ToolContext(
            request_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_id=1,
            correlation_id=uuid.uuid4(),
            logger=logging.getLogger("test_logger"),
            workspace=workspace_path,
            temp_dir=temp_path
        )

        # Traversing upwards out of the workspace directory sandbox
        result = await manager.execute_tool(
            tool=tool,
            arguments={"operation": "read", "path": "../../../etc/passwd"},
            context=context
        )

        assert result.success is False
        assert "Path traversal blocked" in result.error


@pytest.mark.asyncio
async def test_auto_discovery():
    """Verify tool subclasses are auto-discovered on registry initialization."""
    r = ToolRegistry()
    r.clear()
    
    # Run dynamic plug subclass discoverer
    r.discover_plugins()
    assert len(r.list()) > 0
    assert r.exists("browser")
    assert r.exists("python_sandbox")
    assert r.exists("file_system")
    assert r.exists("web_search")
    assert r.exists("calculator")
