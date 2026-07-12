import uuid
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.automation import Plan, TaskStatus
from app.repositories.plan_repository import PlanRepository
from app.repositories.task_repository import TaskRepository
from app.services.automation.task_service import TaskService
from app.services.automation.exceptions import TaskNotFoundError, InvalidStateTransitionError

logger = logging.getLogger("app.services.automation.planning_service")


class PlanningService:
    """Manages the creation and population of task execution plans."""

    def __init__(self):
        self.plan_repo = PlanRepository()
        self.task_repo = TaskRepository()
        self.task_service = TaskService()

    async def create_plan(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int,
        summary: Optional[str],
        steps_data: List[Dict[str, Any]],
        estimated_cost: float = 0.0,
        estimated_duration_sec: int = 0
    ) -> Plan:
        task = await self.task_repo.get_by_id(db, task_id, user_id)
        if not task:
            raise TaskNotFoundError("Task not found or access denied.")

        # Verify task is eligible for planning
        current_status = TaskStatus(task.status)
        if current_status not in [TaskStatus.GOAL_ANALYSIS, TaskStatus.PLANNING, TaskStatus.CREATED, TaskStatus.VALIDATING]:
            raise InvalidStateTransitionError(f"Task status '{task.status}' is not eligible for planning.")

        # Transition task state: Current -> PLANNING (Uses TaskService transitions)
        if current_status != TaskStatus.PLANNING:
            await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.PLANNING)

        try:
            # Create plan base inside transactional scope
            plan = await self.plan_repo.create(db, task_id, summary, estimated_cost, estimated_duration_sec)

            # Create steps
            for step_idx, step_in in enumerate(steps_data):
                await self.plan_repo.create_step(
                    db=db,
                    plan_id=plan.id,
                    step_number=step_idx + 1,
                    tool_name=step_in["tool_name"],
                    input_arguments=step_in.get("arguments", {}),
                    approval_required=step_in.get("approval_required", False)
                )

            await db.flush()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to populate plan steps, rolling back transaction. Error: {e}")
            raise e

        # Transition task state: PLANNING -> PLAN_READY (Uses TaskService transitions)
        # Note: transition_task_status will commit the transaction at the end of state transition!
        await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.PLAN_READY)

        # Retrieve and return plan eager loaded
        stmt = (
            select(Plan)
            .where(Plan.id == plan.id)
            .options(selectinload(Plan.steps))
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    async def get_plan(
        self,
        db: AsyncSession,
        plan_id: uuid.UUID
    ) -> Optional[Plan]:
        return await self.plan_repo.get_by_id(db, plan_id)
