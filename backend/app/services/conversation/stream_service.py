import uuid
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from app.services.conversation.streaming_service import StreamingService


class StreamService:
    """Service layer managing real-time generative streaming response chunks, delegating to StreamingService."""

    def __init__(self):
        self.streaming_service = StreamingService()

    async def generate_response_stream(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: int,
        user_content: str,
        request: Request
    ) -> AsyncGenerator[str, None]:
        """Forward response streaming requests to StreamingService."""
        async for chunk in self.streaming_service.generate_response_stream(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id,
            user_content=user_content,
            request=request
        ):
            yield chunk
