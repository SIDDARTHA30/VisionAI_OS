import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message


class MessageRepository:
    """Repository managing Database operations for the Message model."""

    async def create(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        status: str = "COMPLETED",
        response_time_ms: Optional[int] = None,
        finish_reason: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        is_streamed: bool = False,
        edited: bool = False,
        retry_count: int = 0,
        version: int = 1,
        parent_message_id: Optional[uuid.UUID] = None
    ) -> Message:
        """Insert a new Message record."""
        db_msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            status=status,
            response_time_ms=response_time_ms,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            is_streamed=is_streamed,
            edited=edited,
            retry_count=retry_count,
            version=version,
            parent_message_id=parent_message_id
        )
        db.add(db_msg)
        await db.flush()
        return db_msg

    async def get_by_id(
        self,
        db: AsyncSession,
        message_id: uuid.UUID
    ) -> Optional[Message]:
        """Fetch a specific message by its UUID."""
        stmt = select(Message).where(Message.id == message_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_by_conversation(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[Message]:
        """Fetch the history of messages for a specific conversation, ordered chronologically."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        db: AsyncSession,
        message_id: uuid.UUID,
        status: str
    ) -> Optional[Message]:
        """Update a message's delivery status (e.g. from PENDING to STREAMING or COMPLETED)."""
        db_msg = await self.get_by_id(db, message_id)
        if not db_msg:
            return None
        db_msg.status = status
        db.add(db_msg)
        await db.flush()
        return db_msg

    async def update_metadata(
        self,
        db: AsyncSession,
        message_id: uuid.UUID,
        response_time_ms: int,
        finish_reason: str,
        input_tokens: int,
        output_tokens: int
    ) -> Optional[Message]:
        """Update tokens, processing latency, and completion flags for an assistant message."""
        db_msg = await self.get_by_id(db, message_id)
        if not db_msg:
            return None
        db_msg.response_time_ms = response_time_ms
        db_msg.finish_reason = finish_reason
        db_msg.input_tokens = input_tokens
        db_msg.output_tokens = output_tokens
        db_msg.status = "COMPLETED"
        db.add(db_msg)
        await db.flush()
        return db_msg
