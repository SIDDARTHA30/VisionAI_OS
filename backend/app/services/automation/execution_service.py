import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.automation import Execution, PlanStep, ToolCall, TaskStatus, TaskEvent
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.plan_repository import PlanRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.tool_call_repository import ToolCallRepository
from app.services.automation.task_service import TaskService
from app.tools.manager import ToolManager
from app.services.automation.exceptions import (
    ExecutionNotFoundError,
    TaskNotFoundError,
    InvalidStateTransitionError
)

logger = logging.getLogger("app.services.automation.execution_service")


class ExecutionService:
    """Manages execution instances, workflows tracking, and step executions logs."""

    def __init__(self):
        self.exec_repo = ExecutionRepository()
        self.plan_repo = PlanRepository()
        self.task_repo = TaskRepository()
        self.tool_call_repo = ToolCallRepository()
        self.task_service = TaskService()
        self.tool_manager = ToolManager()

    async def start_execution(
        self,
        db: AsyncSession,
        plan_id: uuid.UUID,
        user_id: int
    ) -> Execution:
        plan = await self.plan_repo.get_by_id(db, plan_id)
        if not plan:
            raise ExecutionNotFoundError("Plan not found.")

        # Verify task is owned and eligible
        task = await self.task_repo.get_by_id(db, plan.task_id, user_id)
        if not task:
            raise TaskNotFoundError("Task access denied.")

        current_status = TaskStatus(task.status)
        if current_status not in [TaskStatus.PLAN_READY, TaskStatus.EXECUTING, TaskStatus.QUEUED, TaskStatus.RETRYING]:
            raise InvalidStateTransitionError(f"Task status '{task.status}' is not eligible for execution.")

        # Transition task to EXECUTING if not already (via TaskService)
        if current_status != TaskStatus.EXECUTING:
            if current_status == TaskStatus.PLAN_READY:
                await self.task_service.transition_task_status(db, plan.task_id, user_id, TaskStatus.QUEUED)
            await self.task_service.transition_task_status(db, plan.task_id, user_id, TaskStatus.EXECUTING)

        try:
            # Create execution log context
            execution = await self.exec_repo.create(db, plan_id)
            execution.status = "EXECUTING"
            execution.started_at = datetime.now(timezone.utc)
            execution.logs = f"[{datetime.now(timezone.utc)}] Execution started for plan {plan_id}.\n"
            db.add(execution)

            event_exec = TaskEvent(
                task_id=task.id,
                event_type="ExecutionStarted",
                payload={"execution_id": str(execution.id), "plan_id": str(plan_id)}
            )
            db.add(event_exec)

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to start execution, rolling back. Error: {e}")
            raise e

        await db.refresh(execution)
        return execution

    async def update_step_execution(
        self,
        db: AsyncSession,
        execution_id: uuid.UUID,
        step_id: uuid.UUID,
        status: str,
        result_output: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> PlanStep:
        execution = await self.exec_repo.get_by_id(db, execution_id)
        if not execution:
            raise ExecutionNotFoundError("Execution context not found.")

        # Fetch step
        from app.models.automation import PlanStep
        res = await db.execute(select(PlanStep).where(PlanStep.id == step_id))
        step = res.scalars().first()
        if not step:
            raise ExecutionNotFoundError("Step not found.")

        current_time = datetime.now(timezone.utc)
        step.status = status
        step.updated_at = datetime.now(timezone.utc)
        if status == "EXECUTING" and not step.started_at:
            step.started_at = current_time
        elif status in ["COMPLETED", "FAILED", "CANCELLED"]:
            step.completed_at = current_time

        if result_output is not None:
            step.result_output = result_output
        if error_message is not None:
            step.error_message = error_message
            
        db.add(step)

        # Append log to execution metrics
        log_entry = f"[{current_time}] Step {step.step_number} ({step.tool_name}) status updated to {status}."
        if error_message:
            log_entry += f" Error: {error_message}"
        execution.logs = (execution.logs or "") + log_entry + "\n"
        db.add(execution)

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to update step execution, rolling back. Error: {e}")
            raise e

        await db.refresh(step)
        return step

    async def record_tool_call(
        self,
        db: AsyncSession,
        step_id: uuid.UUID,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str,
        output: Optional[Dict[str, Any]] = None
    ) -> ToolCall:
        try:
            tool_call = await self.tool_call_repo.create(db, step_id, tool_name, arguments)
            tool_call.status = status
            tool_call.started_at = datetime.now(timezone.utc)
            if status in ["COMPLETED", "FAILED"]:
                tool_call.completed_at = datetime.now(timezone.utc)
                tool_call.output = output
            db.add(tool_call)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to record tool call, rolling back. Error: {e}")
            raise e

        await db.refresh(tool_call)
        return tool_call
        
    async def complete_execution(
        self,
        db: AsyncSession,
        execution_id: uuid.UUID,
        status: str,
        user_id: int
    ) -> Execution:
        execution = await self.exec_repo.get_by_id(db, execution_id)
        if not execution:
            raise ExecutionNotFoundError("Execution context not found.")

        current_time = datetime.now(timezone.utc)
        execution.status = status
        execution.completed_at = current_time
        if execution.started_at:
            execution.duration_sec = int((current_time - execution.started_at).total_seconds())
        execution.logs = (execution.logs or "") + f"[{current_time}] Execution completed with status {status}.\n"
        db.add(execution)

        # Get plan
        plan = await self.plan_repo.get_by_id(db, execution.plan_id)
        if plan:
            # Lifecycle session cleanup: Explicitly clean up all active tool instances registered in this execution plan steps!
            for step in plan.steps:
                try:
                    await self.tool_manager.cleanup_tool(step.tool_name)
                except Exception as cleanup_err:
                    logger.error(f"Error executing cleanup for tool '{step.tool_name}': {cleanup_err}")

            task = await self.task_repo.get_by_id(db, plan.task_id, user_id)
            if task:
                # Update task status strictly using TaskService boundaries (which commits internally!)
                target_task_status = TaskStatus.COMPLETED if status == "COMPLETED" else TaskStatus.FAILED
                await self.task_service.transition_task_status(db, task.id, user_id, target_task_status)

                # Record ExecutionFinished audit event
                event = TaskEvent(
                    task_id=task.id,
                    event_type="ExecutionFinished",
                    payload={"execution_id": str(execution.id), "status": status}
                )
                db.add(event)

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to finalize execution completion, rolling back. Error: {e}")
            raise e

        await db.refresh(execution)
        return execution
