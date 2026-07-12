import uuid
import logging
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.automation import Plan, PlanStep

logger = logging.getLogger(__name__)


class PlanRepository:
    """
    Repository for Plan and PlanStep models.
    Enforces isolation, version history updates, and latest flag checks.
    """

    async def get_by_id(self, db: AsyncSession, plan_id: uuid.UUID) -> Optional[Plan]:
        """Fetch a specific execution plan by its ID."""
        stmt = select(Plan).where(Plan.id == plan_id)
        res = await db.execute(stmt)
        return res.scalars().first()

    async def create_plan_and_steps(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        summary: str,
        steps_list: List[dict],
        estimated_cost: float = 0.0,
        estimated_duration_sec: int = 0,
        parent_plan_id: Optional[uuid.UUID] = None
    ) -> Plan:
        """
        Creates a new plan and associated plan steps.
        Automatically increments the task's plan version history, marks older plans
        as is_latest=False, and saves the new plan as is_latest=True.
        """
        # 1. Deactivate older plans for the same task
        deactivate_stmt = (
            update(Plan)
            .where(Plan.task_id == task_id, Plan.is_latest == True)
            .values(is_latest=False)
        )
        await db.execute(deactivate_stmt)

        # 2. Compute version number increments
        version_stmt = select(Plan).where(Plan.task_id == task_id)
        res = await db.execute(version_stmt)
        existing_plans = res.scalars().all()
        next_version = len(existing_plans) + 1

        # 3. Insert new plan
        new_plan = Plan(
            task_id=task_id,
            summary=summary,
            estimated_cost=estimated_cost,
            estimated_duration_sec=estimated_duration_sec,
            plan_version=next_version,
            is_latest=True,
            parent_plan_id=parent_plan_id
        )
        db.add(new_plan)
        await db.flush()  # Populates new_plan.id

        # 4. Insert steps
        for step in steps_list:
            raw_id = step.get("step_id")
            step_id = uuid.UUID(raw_id) if isinstance(raw_id, str) else (raw_id or uuid.uuid4())
            new_step = PlanStep(
                id=step_id,
                plan_id=new_plan.id,
                step_number=step["step_number"],
                tool_name=step["tool_name"],
                input_arguments=step["input_arguments"],
                approval_required=step["approval_required"],
                depends_on=step.get("depends_on") or [],
                status="PENDING"
            )
            db.add(new_step)

        await db.flush()
        logger.info(f"Successfully saved Plan {new_plan.id} v{new_plan.plan_version} with {len(steps_list)} steps.")
        return new_plan
