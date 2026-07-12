import uuid
import logging
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.automation import Task, TaskStatus, TaskEvent
from app.repositories.task_repository import TaskRepository
from app.services.automation.state_machine import TaskStateMachine
from app.services.automation.exceptions import (
    InvalidStateTransitionError,
    ConcurrencyConflictError,
    TaskNotFoundError
)
from app.events.event_dispatcher import EventDispatcher

logger = logging.getLogger("app.services.automation.task_service")


class TaskService:
    """Manages the creation, status transitions, and lifecycle of automation tasks."""

    def __init__(self):
        self.task_repo = TaskRepository()

    async def create_task(
        self,
        db: AsyncSession,
        user_id: int,
        goal: str,
        conversation_id: Optional[uuid.UUID] = None
    ) -> Task:
        try:
            # Create task inside transactional scope
            task = await self.task_repo.create(db, user_id, goal, conversation_id)
            
            # Log audit event
            event = TaskEvent(
                task_id=task.id,
                event_type="GoalCreated",
                payload={"goal": goal, "conversation_id": str(conversation_id) if conversation_id else None}
            )
            db.add(event)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Task creation failed, transaction rolled back. Error: {e}")
            raise e

        # Dispatch event after successful commit
        EventDispatcher.dispatch(task.id, "TaskCreated", {"task_id": str(task.id), "goal": goal})

        # Eager load relationships to prevent lazy loading errors in serialization
        stmt = (
            select(Task)
            .where(Task.id == task.id)
            .options(selectinload(Task.plans))
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    async def get_task(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int
    ) -> Optional[Task]:
        task = await self.task_repo.get_by_id(db, task_id, user_id)
        if not task:
            raise TaskNotFoundError("Task not found or access denied.")
        return task

    async def list_tasks(
        self,
        db: AsyncSession,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Task]:
        return await self.task_repo.list_by_user(db, user_id, limit, offset)

    async def transition_task_status(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int,
        target_status: TaskStatus
    ) -> Task:
        # Fetch current record
        task = await self.task_repo.get_by_id(db, task_id, user_id)
        if not task:
            raise TaskNotFoundError("Task not found or access denied.")

        current_status = TaskStatus(task.status)
        expected_version = task.version
        
        # Perform state machine validation
        try:
            new_status = TaskStateMachine.transition(current_status, target_status)
        except ValueError as exc:
            raise InvalidStateTransitionError(str(exc))

        # Apply timestamps based on state
        started_at = task.started_at
        completed_at = task.completed_at
        if new_status == TaskStatus.EXECUTING and not started_at:
            started_at = datetime.now(timezone.utc)
        elif new_status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            completed_at = datetime.now(timezone.utc)

        # Update status in DB atomically using optimistic locking
        updated_task = await self.task_repo.update_status(
            db=db,
            task_id=task_id,
            user_id=user_id,
            status=new_status,
            expected_version=expected_version
        )
        
        if not updated_task:
            raise ConcurrencyConflictError(
                f"Concurrency conflict: Task '{task_id}' was updated by another process."
            )

        # Write audit event log to DB
        event = TaskEvent(
            task_id=task_id,
            event_type="StateChanged",
            payload={"from_status": current_status.value, "to_status": new_status.value}
        )
        db.add(event)

        # Commit within Service boundary
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Transaction failed during state transition, rolling back. Error: {e}")
            raise ConcurrencyConflictError(f"Commit failed due to database collision: {e}")

        # Structured state logging
        logger.info({
            "event": "state_transition",
            "task_id": str(task_id),
            "previous_state": current_status.value,
            "new_state": new_status.value,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Event publishing (emit only after successful commit)
        event_mapping = {
            TaskStatus.CREATED: "TaskCreated",
            TaskStatus.PLANNING: "TaskPlanning",
            TaskStatus.EXECUTING: "TaskStarted",
            TaskStatus.WAITING_APPROVAL: "ApprovalRequested",
            TaskStatus.COMPLETED: "TaskCompleted",
            TaskStatus.FAILED: "TaskFailed"
        }
        if new_status in event_mapping:
            EventDispatcher.dispatch(task_id, event_mapping[new_status], {"task_id": str(task_id)})

        # Eager load relationships
        stmt = (
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.plans))
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    async def cancel_task(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int
    ) -> Task:
        return await self.transition_task_status(db, task_id, user_id, TaskStatus.CANCELLED)

    async def retry_task(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int
    ) -> Task:
        return await self.transition_task_status(db, task_id, user_id, TaskStatus.RETRYING)
