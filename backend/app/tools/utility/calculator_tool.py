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


class CalculatorInput(BaseModel):
    expression: str = Field(..., description="Mathematical expression string to evaluate, e.g. '10 + 20 * 2'.")


class CalculatorTool(BaseTool):
    """
    Calculator tool.
    Computes mathematical expressions.
    """

    def __init__(self):
        self._metadata = ToolMetadata(
            name="calculator",
            version="1.0.0",
            author="VisionAI OS Core",
            category=ToolCategory.UTILITY,
            capabilities=[ToolCapability.EXECUTE_CODE],
            description="Evaluates mathematical expressions securely.",
            permissions=[PermissionLevel.SAFE],
            timeout_sec=5,
            tags=["utility", "math", "calculator"]
        )

    @property
    def metadata(self) -> ToolMetadata:
        return self._metadata

    def validate_permissions(self, context: ToolContext) -> None:
        pass

    def validate_input(self, arguments: Dict[str, Any]) -> None:
        try:
            CalculatorInput(**arguments)
        except ValidationError as e:
            raise ToolValidationError(f"Invalid calculator inputs: {e}")

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
        calc_args = CalculatorInput(**arguments)

        expression = calc_args.expression

        # Secure simple eval block (only allow safe math characters)
        allowed_chars = set("0123456789+-*/(). ")
        if not all(c in allowed_chars for c in expression):
            raise ToolValidationError("Invalid math expression. Only digits and math operators are allowed.")

        try:
            # Evaluate math expression
            result = eval(expression, {"__builtins__": None}, {})
            raw_output = str(result)
            success = True
            error_msg = None
            exit_code = 0
            status = ToolStatus.COMPLETED
        except Exception as e:
            raw_output = ""
            success = False
            error_msg = f"Failed to parse calculator expression: {e}"
            exit_code = 1
            status = ToolStatus.FAILED

        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        return ToolResult(
            tool_name=self.metadata.name,
            tool_version=self.metadata.version,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            exit_code=exit_code,
            success=success,
            status=status,
            error=error_msg,
            structured_output={"expression": expression, "result": result if success else None},
            raw_output=raw_output,
            logs=[f"Evaluated math expression: {expression}"]
        )

    async def cleanup(self, context: ToolContext) -> None:
        pass

    async def health_check(self) -> ToolHealth:
        return ToolHealth(
            status="HEALTHY",
            message="Calculator tool is active.",
            dependencies=["eval"],
            latency_ms=1,
            last_checked=datetime.now(timezone.utc)
        )
