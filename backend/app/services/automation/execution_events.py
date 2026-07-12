import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Callable, Awaitable
from pydantic import BaseModel


class ExecutionStarted(BaseModel):
    task_id: uuid.UUID
    plan_id: uuid.UUID
    execution_id: uuid.UUID
    timestamp: datetime = datetime.now(timezone.utc)


class StepStarted(BaseModel):
    task_id: uuid.UUID
    plan_id: uuid.UUID
    execution_id: uuid.UUID
    step_id: uuid.UUID
    step_number: int
    tool_name: str
    timestamp: datetime = datetime.now(timezone.utc)


class StepFinished(BaseModel):
    task_id: uuid.UUID
    plan_id: uuid.UUID
    execution_id: uuid.UUID
    step_id: uuid.UUID
    step_number: int
    tool_name: str
    output: Dict[str, Any]
    timestamp: datetime = datetime.now(timezone.utc)


class StepFailed(BaseModel):
    task_id: uuid.UUID
    plan_id: uuid.UUID
    execution_id: uuid.UUID
    step_id: uuid.UUID
    step_number: int
    tool_name: str
    error: str
    retry_count: int
    timestamp: datetime = datetime.now(timezone.utc)


class TaskCompleted(BaseModel):
    task_id: uuid.UUID
    execution_id: uuid.UUID
    timestamp: datetime = datetime.now(timezone.utc)


class TaskCancelled(BaseModel):
    task_id: uuid.UUID
    execution_id: uuid.UUID
    timestamp: datetime = datetime.now(timezone.utc)


class ExecutionEventEmitter:
    """Dispatches execution lifecycle events to subscribed modules."""

    def __init__(self):
        self._listeners: List[Callable[[BaseModel], Awaitable[None]]] = []

    def subscribe(self, callback: Callable[[BaseModel], Awaitable[None]]):
        self._listeners.append(callback)

    async def emit(self, event: BaseModel):
        for callback in self._listeners:
            try:
                await callback(event)
            except Exception:
                pass


# Global event emitter
execution_events = ExecutionEventEmitter()
