import uuid
from typing import List, Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.automation import Task, TaskStatus, Plan


class TaskRepository:
    """Repository for pure database operations on the Task model."""

    async def create(
        self,
        db: AsyncSession,
        user_id: int,
        goal: str,
        conversation_id: Optional[uuid.UUID] = None
    ) -> Task:
        task = Task(
            user_id=user_id,
            conversation_id=conversation_id,
            goal=goal,
            status=TaskStatus.CREATED,
            version=1
        )
        db.add(task)
        await db.flush()
        return task

    async def get_by_id(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int,
        is_admin: bool = False
    ) -> Optional[Task]:
        filters = [Task.id == task_id, Task.deleted_at.is_(None)]
        if not is_admin:
            filters.append(Task.user_id == user_id)
            
        stmt = (
            select(Task)
            .where(*filters)
            .options(
                selectinload(Task.plans)
                .selectinload(Plan.steps)
            )
        )
        res = await db.execute(stmt)
        return res.scalars().first()

    async def list_by_user(
        self,
        db: AsyncSession,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        is_admin: bool = False
    ) -> List[Task]:
        filters = [Task.deleted_at.is_(None)]
        if not is_admin:
            filters.append(Task.user_id == user_id)

        stmt = (
            select(Task)
            .where(*filters)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Task.plans))
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def update_status(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int,
        status: TaskStatus,
        expected_version: int,
        is_admin: bool = False
    ) -> Optional[Task]:
        filters = [Task.id == task_id, Task.version == expected_version]
        if not is_admin:
            filters.append(Task.user_id == user_id)

        stmt = (
            update(Task)
            .where(*filters)
            .values(
                status=status.value if hasattr(status, "value") else status,
                # SQLAlchemy native version mapper tracks version column automatically,
                # but for atomic UPDATE queries we increment manually
                version=Task.version + 1,
                updated_at=func.now()
            )
            .returning(Task)
        )
        res = await db.execute(stmt)
        return res.scalars().first()
