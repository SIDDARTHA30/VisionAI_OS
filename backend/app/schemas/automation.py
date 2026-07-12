from datetime import datetime
from typing import Any, Dict, List, Optional, Generic, TypeVar
import uuid
from pydantic import BaseModel, Field

from app.models.automation import TaskStatus

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None


class TaskEventResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    event_type: str
    payload: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class ApprovalRequest(BaseModel):
    status: str = Field(..., description="APPROVED or REJECTED")
    rejection_reason: Optional[str] = None


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    step_id: uuid.UUID
    requested_by: Optional[int] = None
    approved_by: Optional[int] = None
    status: str
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    responded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ToolCallResponse(BaseModel):
    id: uuid.UUID
    step_id: uuid.UUID
    tool_name: str
    arguments: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlanStepResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    step_number: int
    tool_name: str
    input_arguments: Dict[str, Any]
    status: str
    approval_required: bool
    error_message: Optional[str] = None
    result_output: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExecutionResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    retry_count: int
    duration_sec: int
    status: str
    logs: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlanResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    summary: Optional[str] = None
    estimated_cost: float
    estimated_duration_sec: int
    created_at: datetime
    updated_at: datetime
    steps: List[PlanStepResponse] = []
    executions: List[ExecutionResponse] = []

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    goal: str = Field(..., min_length=5, description="The primary goal or objective to automate.")
    conversation_id: Optional[uuid.UUID] = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    user_id: int
    conversation_id: Optional[uuid.UUID] = None
    goal: str
    status: TaskStatus
    version: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    plans: List[PlanResponse] = []

    class Config:
        from_attributes = True
