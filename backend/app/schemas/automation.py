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
    depends_on: List[int] = []
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
    plan_version: int
    is_latest: bool
    parent_plan_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    steps: List[PlanStepResponse] = []
    executions: List[ExecutionResponse] = []

    class Config:
        from_attributes = True


# ─── Milestone 4.3: Planner Schemas & Validations ───

from app.tools.enums import ToolCategory, ToolCapability, PermissionLevel


class PlanStepCreate(BaseModel):
    step_id: Optional[uuid.UUID] = None
    step_number: int
    tool_name: str
    input_arguments: Dict[str, Any]
    approval_required: bool
    depends_on: List[int] = []


class PlanCreate(BaseModel):
    summary: str
    confidence_score: float = 1.0
    steps: List[PlanStepCreate]


class PlannerMetadata(BaseModel):
    planner_version: str = "1.0.0"
    prompt_version: str = "1.0.0"
    model_version: str = "gemini-2.5-flash"
    confidence_score: float
    planning_model: str
    generation_time_ms: int
    tokens_used: int


class PlannerMetrics(BaseModel):
    planning_duration_ms: int
    llm_latency_ms: int
    validation_duration_ms: int
    retries: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class PlanningContext(BaseModel):
    conversation_summary: Optional[str] = None
    user_preferences: Dict[str, Any] = {}
    previous_failed_plans: List[uuid.UUID] = []
    available_tools: List[str] = []
    uploaded_files: List[uuid.UUID] = []


class PlannerAuditLog(BaseModel):
    request_id: uuid.UUID
    task_id: uuid.UUID
    plan_id: Optional[uuid.UUID] = None
    latency_ms: int
    model: str
    retries: int
    prompt_tokens: int
    completion_tokens: int
    status: str
    audit_steps: List[str] = []


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
