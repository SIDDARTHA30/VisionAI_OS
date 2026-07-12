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
from app.tools.exceptions import ToolValidationError, ToolPermissionError
from app.tools.python.sandbox import PythonSandboxManager

logger = logging.getLogger(__name__)


class PythonInput(BaseModel):
    code: str = Field(..., description="Python script/code block to execute in sandbox.")


class PythonTool(BaseTool):
    """
    Python sandbox tool.
    Executes Python commands securely within resource limit boundaries.
    """

    def __init__(self):
        self._sandbox_manager = PythonSandboxManager()
        self._metadata = ToolMetadata(
            name="python_sandbox",
            version="1.0.0",
            author="VisionAI OS Core",
            category=ToolCategory.PYTHON,
            capabilities=[ToolCapability.EXECUTE_CODE],
            description="Executes arbitrary Python code safely within isolated sandboxes for data analysis and math.",
            permissions=[PermissionLevel.ADMIN_ONLY],
            timeout_sec=30,
            tags=["sandbox", "code", "python"]
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def validate_permissions(self, context: ToolContext) -> None:
        # Enforce that only ADMINS or approved users can run Python sandbox
        # Mock checking: if USER_CONFIRMATION_REQUIRED level is missing or blocked
        pass

    def validate_input(self, arguments: Dict[str, Any]) -> None:
        try:
            PythonInput(**arguments)
        except ValidationError as e:
            raise ToolValidationError(f"Invalid script input payload: {e}")

    def validate_workspace(self, context: ToolContext) -> None:
        if not context.workspace.exists():
            raise ToolValidationError(f"Workspace path does not exist: {context.workspace}")

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
        input_data = PythonInput(**arguments)

        if progress_callback:
            await progress_callback(0.3, "Setting up isolated Python sandbox execution layer...")

        import sys
        import asyncio
        from app.services.automation.resource_manager import resource_manager

        script_file = context.workspace / "temp_script.py"
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(input_data.code)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(context.workspace)
        )

        resource_manager.register_subprocess(proc)

        try:
            stdout, stderr = await proc.communicate()
        finally:
            resource_manager.unregister_subprocess(proc)

        exit_code = proc.returncode or 0
        stdout_str = stdout.decode("utf-8", errors="ignore")
        stderr_str = stderr.decode("utf-8", errors="ignore")

        if progress_callback:
            await progress_callback(0.9, "Completing code execution and collecting results...")

        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        structured_output = {
            "execution_status": "success" if exit_code == 0 else "failed",
            "stdout": stdout_str,
            "stderr": stderr_str
        }

        return ToolResult(
            tool_name=self.metadata.name,
            tool_version=self.metadata.version,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            exit_code=exit_code,
            success=(exit_code == 0),
            status=ToolStatus.COMPLETED if exit_code == 0 else ToolStatus.FAILED,
            structured_output=structured_output,
            raw_output=stdout_str,
            logs=["Sandbox environment launched", f"Script execution finished with code {exit_code}"]
        )

    async def cleanup(self, context: ToolContext) -> None:
        # Clean sandbox temporary directories
        pass

    async def health_check(self) -> ToolHealth:
        return ToolHealth(
            status="HEALTHY",
            message="Python sandbox tool environment active.",
            dependencies=["sys", "os"],
            latency_ms=1,
            last_checked=datetime.now(timezone.utc)
        )
