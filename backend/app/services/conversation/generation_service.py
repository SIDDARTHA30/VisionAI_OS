import time
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, BackgroundTasks
import logging

from app.models.conversation import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.token_repository import TokenRepository
from app.providers.provider_registry import provider_registry
from app.services.conversation.context_builder import ContextBuilder
from app.services.conversation.prompt_builder import PromptBuilder
from app.services.conversation.status_service import StatusService
from app.services.conversation.memory_service import MemoryService
from app.services.conversation.summary_service import SummaryService
from app.services.conversation.task_worker_service import FastAPIBackgroundTaskQueue
from app.db.redis import redis_client

logger = logging.getLogger(__name__)


class GenerationService:
    """Service layer managing standard synchronous generation runs, costs metrics, and logging."""

    def __init__(self):
        self.conv_repo = ConversationRepository()
        self.msg_repo = MessageRepository()
        self.token_repo = TokenRepository()
        self.context_builder = ContextBuilder()
        self.prompt_builder = PromptBuilder()
        self.status_service = StatusService()
        self.memory_service = MemoryService()
        self.summary_service = SummaryService()

    async def generate_response(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: int,
        user_content: str,
        background_tasks: BackgroundTasks
    ) -> Message:
        """Process chat message synchronously, coordinating locks, history slicing, and provider completion."""
        # 1. Ownership & validation check
        conv = await self.conv_repo.get_by_id(db, conversation_id, user_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or unauthorized access."
            )

        # 2. Acquire Concurrency Lock in Redis
        lock_key = f"lock:conversation:{conversation_id}:generation"
        is_locked = True
        redis_available = True
        try:
            is_locked = await redis_client.set(lock_key, "locked", ex=30, nx=True)
        except Exception as e:
            logger.warning(f"Redis is offline: {str(e)}. Proceeding without lock.")
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
                logger.warning(f"Failed to update status in Redis: {str(e)}")

        settings = conv.settings
        provider_name = "gemini"
        provider = provider_registry.get(provider_name)

        try:
            # 3. Create User Message
            user_msg = await self.msg_repo.create(
                db=db,
                conversation_id=conversation_id,
                role="user",
                content=user_content,
                status="COMPLETED"
            )

            # 4. Create Assistant Placeholder message (PENDING state)
            assistant_msg = await self.msg_repo.create(
                db=db,
                conversation_id=conversation_id,
                role="assistant",
                content="",
                status="PENDING"
            )
            await db.commit()

            # 5. sliding window memory validation & compression
            try:
                await self.memory_service.compress_context_if_needed(db, conversation_id, user_id)
            except Exception as e:
                logger.error(f"Memory context compression failed: {str(e)}")

            # 6. Build Context History
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
                "system_prompt": system_instruction
            }

            # 7. Execute LLM Call with retry logic
            start_time = time.time()
            try:
                ai_response = await provider.generate_response(
                    messages=sliced_context,
                    settings_dict=settings_dict
                )
                finish_reason = "STOP"
                msg_status = "COMPLETED"
            except Exception as e:
                logger.error(f"Failed to generate response: {str(e)}")
                # Update placeholder to prevent hanging PENDING status
                assistant_msg.content = "Failed to generate response."
                await self.msg_repo.update_metadata(
                    db=db,
                    message_id=assistant_msg.id,
                    response_time_ms=int((time.time() - start_time) * 1000),
                    finish_reason="ERROR",
                    input_tokens=0,
                    output_tokens=0
                )
                await self.msg_repo.update_status(db, assistant_msg.id, "FAILED")
                await db.commit()

                err_msg = str(e)
                if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                    retry_delay = "some time"
                    if "retry in" in err_msg:
                        try:
                            retry_delay = err_msg.split("retry in")[1].split("s.")[0].strip() + "s"
                        except Exception:
                            pass
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Gemini API quota exceeded. Please retry after {retry_delay}."
                    )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Gemini API Error: {err_msg}"
                )

            elapsed_ms = int((time.time() - start_time) * 1000)

            # 8. Token counts
            try:
                input_tokens = await provider.count_tokens(sliced_context)
                output_tokens = await provider.count_tokens(ai_response)
            except Exception as e:
                logger.error(f"Failed to count tokens: {str(e)}")
                input_tokens = 0
                output_tokens = 0

            total_tokens = input_tokens + output_tokens
            estimated_cost = ((input_tokens / 1_000_000) * 0.075) + ((output_tokens / 1_000_000) * 0.30)

            # 9. Update Assistant Message
            assistant_msg.content = ai_response
            await self.msg_repo.update_metadata(
                db=db,
                message_id=assistant_msg.id,
                response_time_ms=elapsed_ms,
                finish_reason=finish_reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            await self.msg_repo.update_status(db, assistant_msg.id, msg_status)

            # 10. Record Token Usage
            try:
                await self.token_repo.create(
                    db=db,
                    conversation_id=conversation_id,
                    message_id=assistant_msg.id,
                    provider=provider_name,
                    model=settings.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost=estimated_cost
                )
            except Exception as e:
                logger.error(f"Failed to record token usage: {str(e)}")

            logger.info(
                f"AIChat Metrics - Provider: {provider_name}, Model: {settings.model}, "
                f"Success: True, Latency: {elapsed_ms}ms, Cost: ${estimated_cost:.6f}, "
                f"Input Tokens: {input_tokens}, Output Tokens: {output_tokens}, Total Tokens: {total_tokens}"
            )

            # 11. Update Conversation Counters
            updated_count = conv.message_count + 2
            conv.message_count = updated_count
            conv.last_message_at = datetime.now(timezone.utc)
            db.add(conv)
            await db.commit()

            # 12. Enqueue background tasks via worker queue abstraction
            queue = FastAPIBackgroundTaskQueue(background_tasks)
            queue.enqueue(
                self.summary_service.generate_title_and_summary,
                conversation_id,
                user_id,
                user_content,
                ai_response,
                updated_count
            )

            return assistant_msg

        finally:
            if redis_available:
                try:
                    await redis_client.delete(lock_key)
                    await self.status_service.clear_status(conversation_id)
                except Exception as e:
                    logger.warning(f"Error cleaning lock/status: {str(e)}")
