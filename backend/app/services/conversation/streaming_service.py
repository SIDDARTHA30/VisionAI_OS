import json
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status, Request
import logging

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.token_repository import TokenRepository
from app.providers.provider_registry import provider_registry
from app.services.conversation.context_builder import ContextBuilder
from app.services.conversation.prompt_builder import PromptBuilder
from app.services.conversation.status_service import StatusService
from app.services.conversation.memory_service import MemoryService
from app.db.redis import redis_client

logger = logging.getLogger(__name__)


class StreamingService:
    """Service layer orchestrating Server-Sent Events (SSE) streaming and cancel states management."""

    def __init__(self):
        self.conv_repo = ConversationRepository()
        self.msg_repo = MessageRepository()
        self.token_repo = TokenRepository()
        self.context_builder = ContextBuilder()
        self.prompt_builder = PromptBuilder()
        self.status_service = StatusService()
        self.memory_service = MemoryService()

    async def generate_response_stream(
        self,
        db: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: int,
        user_content: str,
        request: Optional[Request] = None
    ) -> AsyncGenerator[str, None]:
        """Orchestrate chunk generation, yielding formatted SSE payloads to the transport layer."""
        # 1. Retrieve & verify conversation ownership
        conv = await self.conv_repo.get_by_id(db, conversation_id, user_id)
        if not conv:
            yield f"event: error\ndata: {json.dumps({'detail': 'Conversation not found or unauthorized access.'})}\n\n"
            return

        # 2. Concurrency Lock check
        lock_key = f"lock:conversation:{conversation_id}:generation"
        is_locked = True
        redis_available = True
        try:
            is_locked = await redis_client.set(lock_key, "locked", ex=30, nx=True)
        except Exception as e:
            logger.warning(f"Redis is unavailable: {str(e)}. Proceeding without lock.")
            redis_available = False

        if not is_locked:
            yield f"event: error\ndata: {json.dumps({'detail': 'A message is already being generated for this conversation. Please wait.'})}\n\n"
            return

        # Initialize generation status registers
        if redis_available:
            try:
                await self.status_service.clear_cancel(conversation_id)
                await self.status_service.set_status(conversation_id, "THINKING")
            except Exception as e:
                logger.warning(f"Failed to set status in Redis: {str(e)}")

        settings = conv.settings
        provider_name = "gemini"
        provider = provider_registry.get(provider_name)

        # 3. Create User Message in Database
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
            status="PENDING",
            is_streamed=True
        )
        await db.commit()

        # 5. sliding window memory validation & compression
        try:
            await self.memory_service.compress_context_if_needed(db, conversation_id, user_id)
        except Exception as e:
            logger.error(f"Context compression failure: {str(e)}")

        # 6. Build final context
        system_instruction = self.prompt_builder.get_system_prompt(settings.system_prompt or "chat")
        all_messages = await self.msg_repo.list_by_conversation(db, conversation_id)
        
        # Load active versions only for context window representation
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

        # 7. Start Streaming Response
        full_text = []
        start_time = time.time()
        first_token_time = None
        finish_reason = "STOP"
        msg_status = "COMPLETED"
        tokens_generated = 0

        try:
            stream = provider.generate_stream(
                messages=sliced_context,
                settings_dict=settings_dict
            )

            async for chunk in stream:
                # Check Client Disconnect
                if request and await request.is_disconnected():
                    logger.info(f"Client disconnected from stream {conversation_id}")
                    finish_reason = "CANCELLED"
                    msg_status = "CANCELLED"
                    break

                # Check Stop Generation Cancellation signal
                if redis_available:
                    try:
                        if await self.status_service.is_cancelled(conversation_id):
                            logger.info(f"Active generation cancelled by request for {conversation_id}")
                            finish_reason = "CANCELLED"
                            msg_status = "CANCELLED"
                            break
                    except Exception as e:
                        logger.warning(f"Error checking cancellation status: {str(e)}")

                if not first_token_time:
                    first_token_time = time.time()
                    if redis_available:
                        try:
                            await self.status_service.set_status(conversation_id, "STREAMING")
                        except Exception as e:
                            logger.warning(f"Failed to update status in Redis: {str(e)}")

                # Simple token estimates: chunk words count
                tokens_generated += len(chunk.split()) or 1
                if redis_available:
                    try:
                        elapsed = int((time.time() - start_time) * 1000)
                        await self.status_service.set_status(
                            conversation_id,
                            "STREAMING",
                            elapsed_ms=elapsed,
                            tokens_generated=tokens_generated
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update Redis telemetry: {str(e)}")

                full_text.append(chunk)
                yield f"event: token\ndata: {json.dumps({'token': chunk})}\n\n"

            if msg_status != "CANCELLED":
                msg_status = "COMPLETED"
                finish_reason = "STOP"

        except Exception as e:
            logger.error(f"Error yielding SSE stream chunks: {str(e)}")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"
            finish_reason = "ERROR"
            msg_status = "FAILED"

        finally:
            elapsed_ms = int((time.time() - start_time) * 1000)
            final_content = "".join(full_text)

            # Update Assistant Message content and status
            assistant_msg.content = final_content
            assistant_msg.status = msg_status
            assistant_msg.finish_reason = finish_reason

            # Calculate and update token metric fields
            try:
                input_tokens = await provider.count_tokens(sliced_context)
                output_tokens = await provider.count_tokens(final_content) if final_content else 0
            except Exception as e:
                logger.error(f"Failed to count tokens on stream cleanup: {str(e)}")
                input_tokens = 0
                output_tokens = 0

            await self.msg_repo.update_metadata(
                db=db,
                message_id=assistant_msg.id,
                response_time_ms=elapsed_ms,
                finish_reason=finish_reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            # Override database status to match execution final state
            await self.msg_repo.update_status(db, assistant_msg.id, msg_status)

            # Save Token usage analytics
            estimated_cost = ((input_tokens / 1_000_000) * 0.075) + ((output_tokens / 1_000_000) * 0.30)
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
                logger.error(f"Failed to record token usage metrics: {str(e)}")

            # Update conversation count counters
            conv.message_count += 2
            conv.last_message_at = datetime.now(timezone.utc)
            db.add(conv)
            await db.commit()

            # Release Redis locks and clean states
            if redis_available:
                try:
                    await redis_client.delete(lock_key)
                    await self.status_service.clear_status(conversation_id)
                except Exception as e:
                    logger.warning(f"Error cleaning lock/status: {str(e)}")

            # Yield final completion event
            yield f"event: done\ndata: {json.dumps({'finish_reason': finish_reason, 'input_tokens': input_tokens, 'output_tokens': output_tokens})}\n\n"
