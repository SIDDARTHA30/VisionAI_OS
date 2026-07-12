import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Awaitable
from app.tools.base_tool import BaseTool
from app.tools.context import ToolContext
from app.tools.result import ToolResult
from app.tools.enums import ToolStatus
from app.tools.exceptions import (
    ToolError,
    ToolValidationError,
    ToolPermissionError,
    ToolTimeoutError,
    ToolExecutionError,
)

logger = logging.getLogger(__name__)


class ToolManager:
    """
    Coordinator responsible for executing tools safely.
    Handles lifecycle, inputs, permissions, workspaces validations, timeouts, cleanups, and metrics.
    """

    async def execute_tool(
        self,
        tool: BaseTool,
        arguments: Dict[str, Any],
        context: ToolContext,
        progress_callback: Optional[Callable[[float, str], Awaitable[None]]] = None,
    ) -> ToolResult:
        """
        Runs the complete tool execution pipeline under strict lifecycle,
        validation, timeout, and cleanup constraints.
        """
        started_at = datetime.now(timezone.utc)
        tool_name = tool.metadata.name
        tool_version = tool.metadata.version
        logs = []

        def log_info(msg: str):
            logs.append(msg)
            logger.info(f"[{tool_name}] {msg}")

        def log_error(msg: str):
            logs.append(f"ERROR: {msg}")
            logger.error(f"[{tool_name}] {msg}")

        log_info(f"Transitioning tool lifecycle: REGISTERED ──> INITIALIZED")
        log_info(f"Transitioning tool lifecycle: INITIALIZED ──> READY")

        try:
            # 1. Pipeline Validations
            log_info(f"Transitioning tool lifecycle: READY ──> VALIDATING")
            
            log_info("Validating environment...")
            tool.validate_environment()

            log_info("Validating dependencies...")
            tool.validate_dependencies()

            log_info("Validating permissions...")
            tool.validate_permissions(context)

            log_info("Validating workspace...")
            tool.validate_workspace(context)

            log_info("Validating inputs...")
            tool.validate_input(arguments)

            # 2. Execution Setup
            log_info(f"Transitioning tool lifecycle: VALIDATING ──> RUNNING")
            from app.services.automation.execution_policy import execution_policy
            timeout_sec = tool.metadata.timeout_sec or execution_policy.default_timeout_sec

            # 3. Execute with strict timeout limits
            try:
                if hasattr(tool, "before_execute"):
                    log_info("Executing before_execute lifecycle hook...")
                    await tool.before_execute(arguments, context)

                result_output = await asyncio.wait_for(
                    tool.execute(arguments, context, progress_callback),
                    timeout=float(timeout_sec)
                )

                if hasattr(tool, "after_execute") and result_output.success:
                    log_info("Executing after_execute lifecycle hook...")
                    await tool.after_execute(result_output, context)
                
                # Check cancellation token
                if context.cancellation_token:
                    log_info("Tool execution cancelled via token check.")
                    return self._build_result(
                        tool=tool,
                        started_at=started_at,
                        success=False,
                        status=ToolStatus.CANCELLED,
                        error="Execution cancelled via context cancellation token.",
                        logs=logs
                    )

                log_info(f"Transitioning tool lifecycle: RUNNING ──> COMPLETED")
                # Merge inner logs if provided
                if hasattr(result_output, "logs") and result_output.logs:
                    logs.extend(result_output.logs)

                # Return successful result copy with manager logs
                result_output.logs = logs
                return result_output

            except asyncio.TimeoutError as te:
                log_error(f"Execution exceeded timeout limit of {timeout_sec}s.")
                return self._build_result(
                    tool=tool,
                    started_at=started_at,
                    success=False,
                    status=ToolStatus.TIMEOUT,
                    error=f"Tool execution timed out after {timeout_sec} seconds.",
                    logs=logs
                )

        except ToolValidationError as ve:
            log_error(f"Validation failure: {ve.message}")
            return self._build_result(
                tool=tool,
                started_at=started_at,
                success=False,
                status=ToolStatus.FAILED,
                error=ve.message,
                logs=logs
            )
        except ToolPermissionError as pe:
            log_error(f"Permission authorization denied: {pe.message}")
            return self._build_result(
                tool=tool,
                started_at=started_at,
                success=False,
                status=ToolStatus.FAILED,
                error=pe.message,
                logs=logs
            )
        except Exception as e:
            log_error(f"Execution crashed: {str(e)}")
            return self._build_result(
                tool=tool,
                started_at=started_at,
                success=False,
                status=ToolStatus.FAILED,
                error=f"Execution crashed: {str(e)}",
                logs=logs
            )
        finally:
            # 4. Cleanup
            log_info(f"Transitioning tool lifecycle: COMPLETED/FAILED ──> CLEANUP")
            try:
                await tool.cleanup(context)
            except Exception as ce:
                log_error(f"Failed to clean up tool workspaces: {ce}")
            
            log_info(f"Transitioning tool lifecycle: CLEANUP ──> DISPOSED")

    def _build_result(
        self,
        tool: BaseTool,
        started_at: datetime,
        success: bool,
        status: ToolStatus,
        error: Optional[str] = None,
        logs: list = None
    ) -> ToolResult:
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
        return ToolResult(
            tool_name=tool.metadata.name,
            tool_version=tool.metadata.version,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            exit_code=0 if success else 1,
            success=success,
            status=status,
            error=error,
            logs=logs or []
        )
