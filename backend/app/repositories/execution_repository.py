import uuid
from typing import Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import Execution


class ExecutionRepository:
    """Repository for database operations on the Execution model."""

    async def create(
        self,
        db: AsyncSession,
        plan_id: uuid.UUID
    ) -> Execution:
        execution = Execution(
            plan_id=plan_id,
            status="PENDING",
            version=1
        )
        db.add(execution)
        await db.flush()
        return execution

    async def get_by_id(
        self,
        db: AsyncSession,
        execution_id: uuid.UUID
    ) -> Optional[Execution]:
        stmt = select(Execution).where(Execution.id == execution_id)
        res = await db.execute(stmt)
        return res.scalars().first()

    async def update_status(
        self,
        db: AsyncSession,
        execution_id: uuid.UUID,
        status: str,
        expected_version: int,
        logs: Optional[str] = None
    ) -> Optional[Execution]:
        values = {
            "status": status,
            "version": Execution.version + 1,
            "updated_at": func.now()
        }
        if logs is not None:
            values["logs"] = logs

        stmt = (
            update(Execution)
            .where(Execution.id == execution_id, Execution.version == expected_version)
            .values(**values)
            .returning(Execution)
        )
        res = await db.execute(stmt)
        return res.scalars().first()
