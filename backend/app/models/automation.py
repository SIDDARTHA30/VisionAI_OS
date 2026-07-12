import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    JSON,
    Uuid,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


class TaskStatus(str, enum.Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    GOAL_ANALYSIS = "GOAL_ANALYSIS"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


# Valid transitions mapping to enforce state machine rules
VALID_TRANSITIONS: Dict[TaskStatus, List[TaskStatus]] = {
    TaskStatus.CREATED: [TaskStatus.VALIDATING, TaskStatus.CANCELLED],
    TaskStatus.VALIDATING: [TaskStatus.GOAL_ANALYSIS, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.GOAL_ANALYSIS: [TaskStatus.PLANNING, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.PLANNING: [TaskStatus.PLAN_READY, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.PLAN_READY: [TaskStatus.QUEUED, TaskStatus.CANCELLED, TaskStatus.PLANNING],
    TaskStatus.QUEUED: [TaskStatus.EXECUTING, TaskStatus.CANCELLED],
    TaskStatus.EXECUTING: [TaskStatus.WAITING_APPROVAL, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.WAITING_APPROVAL: [TaskStatus.EXECUTING, TaskStatus.CANCELLED, TaskStatus.FAILED],
    TaskStatus.RETRYING: [TaskStatus.EXECUTING, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.FAILED: [TaskStatus.RETRYING, TaskStatus.CANCELLED, TaskStatus.VALIDATING],
    TaskStatus.COMPLETED: [],
    TaskStatus.CANCELLED: [],
}


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    goal = Column(Text, nullable=False)
    status = Column(String(50), default=TaskStatus.CREATED, nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": version}

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="tasks" if hasattr(Base, "_decl_class_registry") and "User" in Base._decl_class_registry else None)
    plans = relationship("Plan", back_populates="task", cascade="all, delete-orphan", lazy="selectin")
    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan", lazy="selectin")


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    task_id = Column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    estimated_cost = Column(Float, default=0.0, nullable=False)
    estimated_duration_sec = Column(Integer, default=0, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    plan_version = Column(Integer, default=1, nullable=False)
    is_latest = Column(Boolean, default=True, nullable=False)
    parent_plan_id = Column(Uuid(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    __mapper_args__ = {"version_id_col": version}

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    task = relationship("Task", back_populates="plans")
    steps = relationship("PlanStep", back_populates="plan", cascade="all, delete-orphan", lazy="selectin")
    executions = relationship("Execution", back_populates="plan", cascade="all, delete-orphan", lazy="selectin")


class PlanStep(Base):
    __tablename__ = "plan_steps"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    plan_id = Column(Uuid(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    tool_name = Column(String(100), nullable=False)
    input_arguments = Column(JSON, default=dict, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, EXECUTING, COMPLETED, FAILED, SKIPPED, CANCELLED
    approval_required = Column(Boolean, default=False, nullable=False)
    depends_on = Column(JSON, default=list, nullable=True)
    error_message = Column(Text, nullable=True)
    result_output = Column(JSON, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": version}

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    plan = relationship("Plan", back_populates="steps")
    tool_calls = relationship("ToolCall", back_populates="step", cascade="all, delete-orphan", lazy="selectin")
    approvals = relationship("Approval", back_populates="step", cascade="all, delete-orphan", lazy="selectin")


class Execution(Base):
    __tablename__ = "executions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    plan_id = Column(Uuid(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    retry_count = Column(Integer, default=0, nullable=False)
    duration_sec = Column(Integer, default=0, nullable=False)
    status = Column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, EXECUTING, COMPLETED, FAILED, CANCELLED
    logs = Column(Text, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": version}

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    plan = relationship("Plan", back_populates="executions")


class TaskEvent(Base):
    __tablename__ = "task_events"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    task_id = Column(Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)  # GoalCreated, PlanGenerated, StateChanged, ToolCalled etc
    payload = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    task = relationship("Task", back_populates="events")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    step_id = Column(Uuid(as_uuid=True), ForeignKey("plan_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    arguments = Column(JSON, default=dict, nullable=False)
    output = Column(JSON, nullable=True)
    status = Column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, EXECUTING, COMPLETED, FAILED
    version = Column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": version}

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    step = relationship("PlanStep", back_populates="tool_calls")


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    step_id = Column(Uuid(as_uuid=True), ForeignKey("plan_steps.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, APPROVED, REJECTED
    rejection_reason = Column(Text, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    __mapper_args__ = {"version_id_col": version}

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    responded_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    step = relationship("PlanStep", back_populates="approvals")


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    steps_definition = Column(JSON, default=list, nullable=False)  # Config definitions for the execution workflow steps
    version = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
