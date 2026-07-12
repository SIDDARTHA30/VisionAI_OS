import uuid
from typing import Any, Dict, Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import ToolCall


class ToolCallRepository:
    """Repository for database operations on the ToolCall model."""

    async def create(
        self,
        db: AsyncSession,
        step_id: uuid.UUID,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> ToolCall:
        tool_call = ToolCall(
            step_id=step_id,
            tool_name=tool_name,
            arguments=arguments,
            status="PENDING",
            version=1
        )
        db.add(tool_call)
        await db.flush()
        return tool_call

    async def update_status(
        self,
        db: AsyncSession,
        tool_call_id: uuid.UUID,
        status: str,
        expected_version: int,
        output: Optional[Dict[str, Any]] = None
    ) -> Optional[ToolCall]:
        values = {
            "status": status,
            "version": ToolCall.version + 1,
            "updated_at": func.now()
        }
        if output is not None:
            values["output"] = output

        stmt = (
            update(ToolCall)
            .where(ToolCall.id == tool_call_id, ToolCall.version == expected_version)
            .values(**values)
            .returning(ToolCall)
        )
        res = await db.execute(stmt)
        return res.scalars().first()
