import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import Approval


class ApprovalRepository:
    """Repository for database operations on the Approval model."""

    async def create(
        self,
        db: AsyncSession,
        step_id: uuid.UUID,
        requested_by: int
    ) -> Approval:
        approval = Approval(
            step_id=step_id,
            requested_by=requested_by,
            status="PENDING",
            version=1
        )
        db.add(approval)
        await db.flush()
        return approval

    async def get_by_id(
        self,
        db: AsyncSession,
        approval_id: uuid.UUID
    ) -> Optional[Approval]:
        stmt = select(Approval).where(Approval.id == approval_id)
        res = await db.execute(stmt)
        return res.scalars().first()

    async def update_status(
        self,
        db: AsyncSession,
        approval_id: uuid.UUID,
        status: str,
        approved_by: int,
        expected_version: int,
        rejection_reason: Optional[str] = None
    ) -> Optional[Approval]:
        stmt = (
            update(Approval)
            .where(Approval.id == approval_id, Approval.version == expected_version)
            .values(
                status=status,
                approved_by=approved_by,
                rejection_reason=rejection_reason,
                version=Approval.version + 1,
                responded_at=datetime.now(timezone.utc),
                updated_at=func.now()
            )
            .returning(Approval)
        )
        res = await db.execute(stmt)
        return res.scalars().first()
