import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks

from app.models.conversation import Message
from app.services.conversation.generation_service import GenerationService

logger = logging.getLogger(__name__)


class AIChatService:
    """Service layer managing standard synchronous generation requests, delegating to GenerationService."""

    def __init__(self):
        self.generation_service = GenerationService()

    async def send_message(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: int,
        user_content: str,
        background_tasks: BackgroundTasks
    ) -> Message:
        """Forward message submission and coordinate response creation via GenerationService."""
        return await self.generation_service.generate_response(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id,
            user_content=user_content,
            background_tasks=background_tasks
        )
