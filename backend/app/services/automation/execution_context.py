import uuid
from pathlib import Path
from typing import Any, Dict
from pydantic import BaseModel, ConfigDict


class ExecutionContext(BaseModel):
    """Active runtime context container for task execution."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: uuid.UUID
    task_id: uuid.UUID
    plan_id: uuid.UUID
    execution_id: uuid.UUID
    user_id: int
    workspace: Path
    temp_dir: Path
    variables: Dict[str, Any] = {}
    is_cancelled: bool = False
