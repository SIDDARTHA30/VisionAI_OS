import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.conversation_repository import ConversationRepository
from app.providers.provider_registry import provider_registry

logger = logging.getLogger(__name__)


class SummaryService:
    """Service layer managing conversation titles generation and background summarizations updates."""

    def __init__(self):
        self.conv_repo = ConversationRepository()

    async def generate_title_and_summary(
        self,
        conversation_id: uuid.UUID,
        user_id: int,
        user_content: str,
        ai_response: str,
        message_count: int
    ) -> None:
        """Run post-response analytics to auto-generate titles and summaries using a fresh database session."""
        from app.db.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            conv = await self.conv_repo.get_by_id(db, conversation_id, user_id)
            if not conv:
                return

            provider = provider_registry.get("gemini")

            # 1. Check for auto-naming: Rename title if it's the first exchange
            if message_count <= 2:
                rename_prompt = (
                    "Summarize the following conversation initiation prompt in a concise, "
                    "professional title of 2 to 5 words. Do not wrap in quotes or add markdown formatting.\n"
                    f"User: {user_content}"
                )
                settings_dict = {
                    "model": conv.settings.model,
                    "temperature": 0.3,
                    "max_tokens": 15
                }
                try:
                    title_candidate = await provider.generate_response(
                        messages=[{"role": "user", "content": rename_prompt}],
                        settings_dict=settings_dict
                    )
                    clean_title = title_candidate.strip().replace('"', '')
                    if clean_title:
                        await self.conv_repo.update_title(db, conversation_id, user_id, clean_title)
                        logger.info(f"Auto-renamed conversation {conversation_id} to: '{clean_title}'")
                except Exception as ex:
                    logger.error(f"Failed to auto-rename conversation {conversation_id}: {str(ex)}")

            # 2. Check for auto-summarization: Update summary on each exchange
            summary_prompt = (
                "Provide a brief, single-sentence summary of the conversation so far, "
                "capturing key topics. Do not use quotes or introductory phrases.\n"
                f"User: {user_content}\nAssistant: {ai_response}"
            )
            settings_dict = {
                "model": conv.settings.model,
                "temperature": 0.3,
                "max_tokens": 60
            }
            try:
                summary_candidate = await provider.generate_response(
                    messages=[{"role": "user", "content": summary_prompt}],
                    settings_dict=settings_dict
                )
                clean_summary = summary_candidate.strip()
                await self.conv_repo.update_summary_and_counts(
                    db=db,
                    conversation_id=conversation_id,
                    summary=clean_summary,
                    message_count=message_count,
                    last_message_at=datetime.now(timezone.utc)
                )
                logger.info(f"Auto-summarized conversation {conversation_id} successfully.")
            except Exception as ex:
                logger.error(f"Failed to auto-summarize conversation {conversation_id}: {str(ex)}")
            
            await db.commit()
