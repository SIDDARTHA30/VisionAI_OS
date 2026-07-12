from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from app.tools.enums import ToolStatus


class ToolResult(BaseModel):
    tool_name: str
    tool_version: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    exit_code: int
    success: bool
    status: ToolStatus
    error: Optional[str] = None
    warnings: List[str] = []
    logs: List[str] = []
    structured_output: Dict[str, Any] = {}
    raw_output: Optional[str] = None
    artifacts: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True
    )
