import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.ai_config import ai_config
from app.models.conversation import Conversation, ConversationSetting, Message
from app.models.user import User


class ConversationRepository:
    """Repository managing Database operations for the Conversation model."""

    async def create(
        self, 
        db: AsyncSession, 
        user_id: int, 
        title: str, 
        settings_dict: Dict[str, Any]
    ) -> Conversation:
        """Create a new Conversation and initialize its settings."""
        db_conv = Conversation(
            user_id=user_id,
            title=title,
            is_deleted=False
        )
        db.add(db_conv)
        await db.flush()  # Generate UUID ID

        db_settings = ConversationSetting(
            conversation_id=db_conv.id,
            model=settings_dict.get("model", ai_config.GEMINI_MODEL),
            temperature=settings_dict.get("temperature", ai_config.GEMINI_TEMPERATURE),
            max_tokens=settings_dict.get("max_tokens", ai_config.GEMINI_MAX_TOKENS),
            language=settings_dict.get("language", "en"),
            system_prompt=settings_dict.get("system_prompt", None),
            stream_enabled=settings_dict.get("stream_enabled", True)
        )
        db.add(db_settings)
        await db.flush()
        
        # Load relationships cleanly
        db_conv.settings = db_settings
        return db_conv

    async def get_by_id(
        self, 
        db: AsyncSession, 
        conversation_id: uuid.UUID, 
        user_id: int
    ) -> Optional[Conversation]:
        """Fetch an active conversation by ID and user ownership."""
        stmt = (
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.is_deleted == False
            )
            .options(selectinload(Conversation.settings))
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_active_by_user(
        self, 
        db: AsyncSession, 
        user_id: int, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Conversation]:
        """List active non-deleted conversations for a user, sorted by recency."""
        stmt = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.is_deleted == False
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Conversation.settings))
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_title(
        self, 
        db: AsyncSession, 
        conversation_id: uuid.UUID, 
        user_id: int, 
        new_title: str
    ) -> Optional[Conversation]:
        """Update conversation title."""
        db_conv = await self.get_by_id(db, conversation_id, user_id)
        if not db_conv:
            return None
        db_conv.title = new_title
        db_conv.updated_at = datetime.now(timezone.utc)
        db.add(db_conv)
        await db.flush()
        return db_conv

    async def soft_delete(
        self, 
        db: AsyncSession, 
        conversation_id: uuid.UUID, 
        user_id: int
    ) -> bool:
        """Mark a conversation as deleted (soft delete)."""
        db_conv = await self.get_by_id(db, conversation_id, user_id)
        if not db_conv:
            return False
        db_conv.is_deleted = True
        db_conv.updated_at = datetime.now(timezone.utc)
        db.add(db_conv)
        await db.flush()
        return True

    async def update_summary_and_counts(
        self, 
        db: AsyncSession, 
        conversation_id: uuid.UUID, 
        summary: str, 
        message_count: int,
        last_message_at: datetime
    ) -> None:
        """Update summary metrics inside background execution tasks."""
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                summary=summary,
                message_count=message_count,
                last_message_at=last_message_at,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await db.execute(stmt)

    async def search_conversations(
        self, 
        db: AsyncSession, 
        user_id: int, 
        query_str: str, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Conversation]:
        """Search conversations by title, summary, or nested message contents."""
        match_pattern = f"%{query_str}%"
        # Subquery to search matching messages ids
        msg_stmt = select(Message.conversation_id).where(Message.content.ilike(match_pattern))
        
        stmt = (
            select(Conversation)
            .where(
                Conversation.user_id == user_id,
                Conversation.is_deleted == False,
                or_(
                    Conversation.title.ilike(match_pattern),
                    Conversation.summary.ilike(match_pattern),
                    Conversation.id.in_(msg_stmt)
                )
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Conversation.settings))
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
