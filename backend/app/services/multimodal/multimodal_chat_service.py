"""
Module 3 — MultimodalChatService: Vision-aware conversation continuation.

Enables users to send messages that reference pre-uploaded FileAssets alongside text.
The context builder incorporates image/file references in the Gemini contents list.
Reuses GenerationService metrics, MemoryService compression, and the same MessageResponse schema.
No breaking changes to existing conversation endpoints.
"""
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message
from app.models.file_asset import FileAsset
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.token_repository import TokenRepository
from app.repositories.file_repository import FileRepository
from app.providers.provider_registry import provider_registry
from app.services.conversation.context_builder import ContextBuilder
from app.services.conversation.prompt_builder import PromptBuilder
from app.services.conversation.status_service import StatusService
from app.services.conversation.memory_service import MemoryService
from app.services.conversation.summary_service import SummaryService
from app.services.conversation.task_worker_service import FastAPIBackgroundTaskQueue
from app.db.redis import redis_client

logger = logging.getLogger(__name__)


class MultimodalChatService:
    """
    Handles multimodal chat messages that combine text with one or more file attachments.
    The response schema is identical to the standard MessageResponse — no client-side changes required.
    """

    def __init__(self):
        self.conv_repo = ConversationRepository()
        self.msg_repo = MessageRepository()
        self.token_repo = TokenRepository()
        self.file_repo = FileRepository()
        self.context_builder = ContextBuilder()
        self.prompt_builder = PromptBuilder()
        self.status_service = StatusService()
        self.memory_service = MemoryService()
        self.summary_service = SummaryService()

    async def send_multimodal_message(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: int,
        user_content: str,
        file_ids: List[uuid.UUID],
        background_tasks: BackgroundTasks,
    ) -> Message:
        """
        Process a multimodal chat message combining text + file attachments.

        Flow:
        1. Validate conversation ownership.
        2. Acquire Redis concurrency lock.
        3. Resolve and validate each FileAsset (must be READY and owned by the user).
        4. Create user message with file attachments.
        5. Build context including text history + multimodal content parts.
        6. Call Gemini with mixed text + file content.
        7. Persist assistant response and metrics.
        8. Enqueue background title/summary generation.
        """
        # 1. Validate conversation
        conv = await self.conv_repo.get_by_id(db, conversation_id, user_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or unauthorized access."
            )

        # 2. Redis concurrency lock (same pattern as GenerationService)
        lock_key = f"lock:conversation:{conversation_id}:generation"
        is_locked = True
        redis_available = True
        try:
            is_locked = await redis_client.set(lock_key, "locked", ex=30, nx=True)
        except Exception as e:
            logger.warning(f"Redis offline: {e}. Proceeding without lock.")
            redis_available = False

        if not is_locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A message is already being generated for this conversation. Please wait."
            )

        if redis_available:
            try:
                await self.status_service.clear_cancel(conversation_id)
                await self.status_service.set_status(conversation_id, "THINKING")
            except Exception as e:
                logger.warning(f"Failed to update Redis status: {e}")

        settings = conv.settings
        provider_name = "gemini"
        provider = provider_registry.get(provider_name)

        try:
            # 3. Resolve FileAssets — validate ownership and READY status
            file_assets: List[FileAsset] = []
            for fid in file_ids:
                asset = await self.file_repo.get_by_id_and_user(db, fid, user_id)
                if not asset:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"File {fid} not found or does not belong to you."
                    )
                if asset.status != "READY":
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"File {fid} is not ready (status: {asset.status}). "
                               f"Wait for READY before attaching to a message."
                    )
                file_assets.append(asset)

            # 4. Persist user message
            user_msg = await self.msg_repo.create(
                db=db,
                conversation_id=conversation_id,
                role="user",
                content=user_content,
                status="COMPLETED",
            )

            # Attach files to user message
            for asset in file_assets:
                await self.file_repo.attach_to_message(
                    db=db,
                    message_id=user_msg.id,
                    file_asset_id=asset.id,
                )

            # 5. Create assistant placeholder
            assistant_msg = await self.msg_repo.create(
                db=db,
                conversation_id=conversation_id,
                role="assistant",
                content="",
                status="PENDING",
            )
            await db.commit()

            # Memory compression
            try:
                await self.memory_service.compress_context_if_needed(db, conversation_id, user_id)
            except Exception as e:
                logger.error(f"Memory compression failed: {e}")

            # 6. Build text context history
            system_instruction = self.prompt_builder.get_system_prompt(settings.system_prompt or "chat")
            all_messages = await self.msg_repo.list_by_conversation(db, conversation_id)
            context_messages = [m for m in all_messages if m.id != assistant_msg.id and m.is_active]
            sliced_context = self.context_builder.build_context(
                messages=context_messages,
                max_input_tokens=settings.max_tokens
            )

            settings_dict = {
                "model": settings.model,
                "temperature": settings.temperature,
                "max_tokens": settings.max_tokens,
                "system_prompt": system_instruction,
            }

            # 7. Execute multimodal LLM call
            start_time = time.time()
            try:
                # Delegate to provider's multimodal generation
                ai_response = await provider.generate_multimodal_response(
                    messages=sliced_context,
                    file_assets=[
                        {"gemini_file_name": a.gemini_file_name, "mime_type": a.mime_type}
                        for a in file_assets
                    ],
                    user_text=user_content,
                    settings_dict=settings_dict,
                )
                finish_reason = "STOP"
                msg_status = "COMPLETED"
            except Exception as e:
                logger.error(f"Multimodal generation failed: {e}")
                await self.msg_repo.update_metadata(
                    db=db,
                    message_id=assistant_msg.id,
                    response_time_ms=int((time.time() - start_time) * 1000),
                    finish_reason="ERROR",
                    input_tokens=0,
                    output_tokens=0,
                )
                await self.msg_repo.update_status(db, assistant_msg.id, "FAILED")
                await db.commit()

                err_msg = str(e)
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Gemini API quota exceeded: {err_msg}"
                    )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Multimodal generation error: {err_msg}"
                )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Token counting (best effort)
            try:
                input_tokens = await provider.count_tokens(sliced_context)
                output_tokens = await provider.count_tokens(ai_response)
            except Exception:
                input_tokens = 0
                output_tokens = 0

            total_tokens = input_tokens + output_tokens
            estimated_cost = ((input_tokens / 1_000_000) * 0.075) + ((output_tokens / 1_000_000) * 0.30)

            # 8. Update assistant message
            assistant_msg.content = ai_response
            await self.msg_repo.update_metadata(
                db=db,
                message_id=assistant_msg.id,
                response_time_ms=elapsed_ms,
                finish_reason=finish_reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            await self.msg_repo.update_status(db, assistant_msg.id, msg_status)

            # Record token usage
            try:
                await self.token_repo.create(
                    db=db,
                    conversation_id=conversation_id,
                    message_id=assistant_msg.id,
                    provider=provider_name,
                    model=settings.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost=estimated_cost,
                )
            except Exception as e:
                logger.error(f"Failed to record token usage: {e}")

            logger.info(
                f"MultimodalChat Metrics - Provider: {provider_name}, Model: {settings.model}, "
                f"Files: {len(file_assets)}, Latency: {elapsed_ms}ms, "
                f"Cost: ${estimated_cost:.6f}, Tokens: {total_tokens}"
            )

            # Update conversation counters
            conv.message_count += 2
            conv.last_message_at = datetime.now(timezone.utc)
            db.add(conv)
            await db.commit()

            # Background summary/title generation
            queue = FastAPIBackgroundTaskQueue(background_tasks)
            queue.enqueue(
                self.summary_service.generate_title_and_summary,
                conversation_id,
                user_id,
                user_content,
                ai_response,
                conv.message_count,
            )

            return assistant_msg

        finally:
            if redis_available:
                try:
                    await redis_client.delete(lock_key)
                    await self.status_service.clear_status(conversation_id)
                except Exception as e:
                    logger.warning(f"Error cleaning up Redis lock/status: {e}")
