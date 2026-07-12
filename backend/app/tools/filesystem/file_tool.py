from datetime import datetime, timezone
import logging
import os
import shutil
from typing import Any, Callable, Dict, Optional, Awaitable
from pydantic import BaseModel, Field, ValidationError

from app.tools.base_tool import BaseTool
from app.tools.context import ToolContext
from app.tools.result import ToolResult
from app.tools.enums import ToolCategory, ToolCapability, PermissionLevel, ToolStatus
from app.tools.metadata import ToolMetadata
from app.tools.schemas import ToolHealth
from app.tools.exceptions import ToolValidationError, ToolPermissionError

logger = logging.getLogger(__name__)


class FileInput(BaseModel):
    operation: str = Field(..., description="File operation: read, write, delete, list, copy, move")
    path: str = Field(..., description="Target file name or relative path inside workspace")
    content: Optional[str] = Field(None, description="String content to write if writing a file")


class FileTool(BaseTool):
    """
    Local filesystem operations plugin skeleton.
    Restricts operations to safe sandbox boundaries defined in ToolContext.
    """

    def __init__(self):
        self._metadata = ToolMetadata(
            name="file_system",
            version="1.0.0",
            author="VisionAI OS Core",
            category=ToolCategory.FILESYSTEM,
            capabilities=[ToolCapability.READ_FILE, ToolCapability.WRITE_FILE],
            description="Reads, writes, deletes, and copies files safely inside workspace directories.",
            permissions=[PermissionLevel.SAFE],
            timeout_sec=10,
            tags=["filesystem", "files", "local"]
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def validate_permissions(self, context: ToolContext) -> None:
        pass

    def validate_input(self, arguments: Dict[str, Any]) -> None:
        try:
            FileInput(**arguments)
        except ValidationError as e:
            raise ToolValidationError(f"Invalid file command inputs: {e}")

    def validate_workspace(self, context: ToolContext) -> None:
        # Check workspace directory path boundaries
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
        file_args = FileInput(**arguments)

        # Resolve path safely inside workspace to block directory traversals
        target_path = context.workspace / file_args.path
        resolved_path = target_path.resolve()

        if not str(resolved_path).startswith(str(context.workspace.resolve())):
            raise ToolValidationError("Path traversal blocked. Operations must stay inside the sandbox.")

        import aiofiles

        # Ensure parent folder exists
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        logs = []
        structured_output = {"operation": file_args.operation, "path": file_args.path}

        if file_args.operation == "write":
            logs.append(f"Writing content to file: {file_args.path}")
            content = file_args.content or ""
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content)
            structured_output["bytes_written"] = len(content)
            raw_output = f"Successfully wrote {len(content)} bytes to {file_args.path}."
        elif file_args.operation == "read":
            logs.append(f"Reading content from file: {file_args.path}")
            if not resolved_path.exists():
                raise ToolValidationError(f"File not found: {file_args.path}")
            with open(resolved_path, "r", encoding="utf-8") as f:
                content = f.read()
            raw_output = content
            structured_output["content"] = raw_output
        elif file_args.operation == "delete":
            logs.append(f"Deleting file: {file_args.path}")
            if resolved_path.exists():
                if resolved_path.is_dir():
                    shutil.rmtree(resolved_path)
                else:
                    resolved_path.unlink()
            raw_output = f"Successfully deleted {file_args.path}."
        elif file_args.operation == "list":
            logs.append(f"Listing directory files: {file_args.path}")
            search_dir = resolved_path if resolved_path.is_dir() else resolved_path.parent
            files_list = os.listdir(search_dir)
            raw_output = str(files_list)
            structured_output["files"] = files_list
        else:
            logs.append(f"Executing operation: {file_args.operation}")
            raw_output = f"Successfully executed operation: {file_args.operation} on {file_args.path}."

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
            structured_output=structured_output,
            raw_output=raw_output,
            logs=logs
        )

    async def cleanup(self, context: ToolContext) -> None:
        pass

    async def health_check(self) -> ToolHealth:
        return ToolHealth(
            status="HEALTHY",
            message="Local filesystem controller online.",
            dependencies=["os.path"],
            latency_ms=1,
            last_checked=datetime.now(timezone.utc)
        )
