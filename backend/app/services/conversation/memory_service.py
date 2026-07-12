import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.providers.provider_registry import provider_registry
from app.core.ai_config import ai_config

logger = logging.getLogger(__name__)


class MemoryService:
    """Service layer responsible for context tracking, sliding windows, and auto-summarization compression."""

    def __init__(self):
        self.conv_repo = ConversationRepository()
        self.msg_repo = MessageRepository()

    async def compress_context_if_needed(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: int
    ) -> Optional[str]:
        """Check token usage of active messages; if it exceeds 75-80% of context limits, generate summary."""
        conv = await self.conv_repo.get_by_id(db, conversation_id, user_id)
        if not conv:
            return None

        settings = conv.settings
        provider_name = "gemini"
        provider = provider_registry.get(provider_name)

        # Retrieve active messages (non-deleted, active versions)
        all_messages = await self.msg_repo.list_by_conversation(db, conversation_id)
        active_messages = [m for m in all_messages if m.is_active and m.status == "COMPLETED"]

        if not active_messages:
            return conv.summary

        # Map active messages list for token calculations
        mapped_messages = [{"role": m.role, "content": m.content} for m in active_messages]
        try:
            total_tokens = await provider.count_tokens(mapped_messages)
        except Exception as e:
            logger.error(f"Failed to count tokens in memory service: {str(e)}")
            total_tokens = 0

        # Summarization context trigger threshold: 75% of limit
        model_limit = 1000000  # Default model limit
        limit = min(settings.max_tokens, model_limit)
        threshold = int(limit * 0.75)

        logger.info(
            f"Memory audit - Conversation: {conversation_id}, "
            f"Active tokens: {total_tokens}, Threshold: {threshold}"
        )

        if total_tokens > threshold and len(active_messages) > 4:
            logger.info(f"Context threshold exceeded ({total_tokens} > {threshold}). Compressing context...")

            # Compress the oldest 50% of the active messages
            num_to_compress = len(active_messages) // 2
            messages_to_compress = active_messages[:num_to_compress]

            # Generate updated summary combining prior summary with compressed message lines
            old_summary = conv.summary or ""
            summary_prompt = (
                f"Compile a single concise paragraph summarizing the following conversation history. "
                f"Prior Summary: '{old_summary}'. "
                f"New messages to integrate:\n" +
                "\n".join([f"{m.role}: {m.content}" for m in messages_to_compress])
            )

            try:
                new_summary = await provider.generate_response(
                    messages=[{"role": "user", "content": summary_prompt}],
                    settings_dict={"model": settings.model, "temperature": 0.5}
                )
            except Exception as e:
                logger.error(f"Failed to generate summary context: {str(e)}")
                return conv.summary

            # Deactivate compressed messages in database
            for m in messages_to_compress:
                m.is_active = False
                db.add(m)

            # Update conversation summary metadata
            conv.summary = new_summary
            await db.flush()
            logger.info(f"Context compression complete. Summary length: {len(new_summary)}")
            return new_summary

        return conv.summary
