import uuid
from typing import Any, Dict, Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.automation import Plan, PlanStep


class PlanRepository:
    """Repository for pure database operations on Plan and PlanStep models."""

    async def create(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        summary: Optional[str],
        estimated_cost: float = 0.0,
        estimated_duration_sec: int = 0
    ) -> Plan:
        plan = Plan(
            task_id=task_id,
            summary=summary,
            estimated_cost=estimated_cost,
            estimated_duration_sec=estimated_duration_sec,
            version=1
        )
        db.add(plan)
        await db.flush()
        return plan

    async def get_by_id(
        self,
        db: AsyncSession,
        plan_id: uuid.UUID
    ) -> Optional[Plan]:
        stmt = (
            select(Plan)
            .where(Plan.id == plan_id)
            .options(
                selectinload(Plan.steps),
                selectinload(Plan.executions)
            )
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    async def create_step(
        self,
        db: AsyncSession,
        plan_id: uuid.UUID,
        step_number: int,
        tool_name: str,
        input_arguments: Dict[str, Any],
        approval_required: bool = False
    ) -> PlanStep:
        step = PlanStep(
            plan_id=plan_id,
            step_number=step_number,
            tool_name=tool_name,
            input_arguments=input_arguments,
            approval_required=approval_required,
            status="PENDING",
            version=1
        )
        db.add(step)
        await db.flush()
        return step

    async def update_step_status(
        self,
        db: AsyncSession,
        step_id: uuid.UUID,
        status: str,
        expected_version: int,
        result_output: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Optional[PlanStep]:
        values = {
            "status": status,
            "version": PlanStep.version + 1,
            "updated_at": func.now()
        }
        if result_output is not None:
            values["result_output"] = result_output
        if error_message is not None:
            values["error_message"] = error_message

        stmt = (
            update(PlanStep)
            .where(PlanStep.id == step_id, PlanStep.version == expected_version)
            .values(**values)
            .returning(PlanStep)
        )
        res = await db.execute(stmt)
        return res.scalars().first()
