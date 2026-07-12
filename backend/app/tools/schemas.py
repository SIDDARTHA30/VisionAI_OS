from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class ToolHealth(BaseModel):
    status: str  # HEALTHY, UNHEALTHY, DEGRADED
    message: Optional[str] = None
    dependencies: List[str] = []
    latency_ms: int
    last_checked: datetime

    model_config = ConfigDict(
        validate_assignment=True
    )
