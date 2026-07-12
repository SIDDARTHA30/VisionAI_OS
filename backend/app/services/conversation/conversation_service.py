import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.repositories.conversation_repository import ConversationRepository
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)


class ConversationService:
    """Service layer managing business logic for Conversation CRUD and session configurations."""

    def __init__(self):
        self.repo = ConversationRepository()

    async def create_conversation(
        self, 
        db: AsyncSession, 
        user_id: int, 
        title: str, 
        settings: Dict[str, Any]
    ) -> Conversation:
        """Create a new session, initializing title and model configurations."""
        logger.info(f"Creating new conversation for user {user_id} with title: '{title}'")
        conv = await self.repo.create(db, user_id, title, settings)
        return conv

    async def get_conversation(
        self, 
        db: AsyncSession, 
        conversation_id: uuid.UUID, 
        user_id: int
    ) -> Optional[Conversation]:
        """Load conversation with validation check."""
        return await self.repo.get_by_id(db, conversation_id, user_id)

    async def list_conversations(
        self, 
        db: AsyncSession, 
        user_id: int, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Conversation]:
        """Fetch active paginated sessions list for a user."""
        return await self.repo.list_active_by_user(db, user_id, limit, offset)

    async def rename_conversation(
        self, 
        db: AsyncSession, 
        conversation_id: uuid.UUID, 
        user_id: int, 
        new_title: str
    ) -> Optional[Conversation]:
        """Change the name of a conversation session."""
        logger.info(f"Renaming conversation {conversation_id} to '{new_title}'")
        return await self.repo.update_title(db, conversation_id, user_id, new_title)

    async def delete_conversation(
        self, 
        db: AsyncSession, 
        conversation_id: uuid.UUID, 
        user_id: int
    ) -> bool:
        """Soft delete a conversation session."""
        logger.info(f"Soft-deleting conversation {conversation_id}")
        return await self.repo.soft_delete(db, conversation_id, user_id)

    async def search_conversations(
        self, 
        db: AsyncSession, 
        user_id: int, 
        query: str, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Conversation]:
        """Search conversations by title, messages, or summary contents."""
        logger.info(f"User {user_id} executing conversation search query: '{query}'")
        return await self.repo.search_conversations(db, user_id, query, limit, offset)
