import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict


class ToolContext(BaseModel):
    request_id: uuid.UUID
    trace_id: uuid.UUID
    session_id: uuid.UUID
    task_id: Optional[uuid.UUID] = None
    plan_id: Optional[uuid.UUID] = None
    step_id: Optional[uuid.UUID] = None
    user_id: int
    execution_id: Optional[uuid.UUID] = None
    correlation_id: uuid.UUID
    cancellation_token: bool = False
    logger: Any  # Accept standard Python or structural Loggers
    workspace: Path
    temp_dir: Path
    config: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    shared_memory: Dict[str, Any] = {}

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True
    )
