from datetime import datetime, timezone
from typing import Any, Dict
import uuid
from pydantic import BaseModel, Field


class AutomationEvent(BaseModel):
    """Placeholder schema for automation execution flow event events."""
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    task_id: uuid.UUID
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
