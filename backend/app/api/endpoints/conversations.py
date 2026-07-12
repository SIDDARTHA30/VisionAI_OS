import uuid
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
    FeedbackCreate
)
from app.services.conversation.conversation_service import ConversationService
from app.services.conversation.ai_chat_service import AIChatService
from app.services.conversation.stream_service import StreamService
from app.services.conversation.status_service import StatusService
from app.services.conversation.export_service import ExportService
from app.repositories.message_repository import MessageRepository
from app.db.redis import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()
msg_router = APIRouter()

conv_service = ConversationService()
chat_service = AIChatService()
stream_service = StreamService()
status_service = StatusService()
export_service = ExportService()
msg_repo = MessageRepository()


@router.post("/", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new conversation session with custom model settings."""
    settings_dict = payload.settings.model_dump() if payload.settings else {}
    conv = await conv_service.create_conversation(
        db=db,
        user_id=current_user.id,
        title=payload.title,
        settings=settings_dict
    )
    await db.commit()
    full_conv = await conv_service.get_conversation(db, conv.id, current_user.id)
    return full_conv


@router.get("/", response_model=List[ConversationResponse])
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List active (non-deleted) conversations for the authenticated user."""
    return await conv_service.list_conversations(
        db=db,
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )


@router.get("/search", response_model=List[ConversationResponse])
async def search_conversations(
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search conversations across title, summary, and message histories."""
    return await conv_service.search_conversations(
        db=db,
        user_id=current_user.id,
        query=query,
        limit=limit,
        offset=offset
    )


@router.get("/{id}", response_model=ConversationResponse)
async def get_conversation(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve detailed conversation configurations and states."""
    conv = await conv_service.get_conversation(db=db, conversation_id=id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )
    return conv


@router.put("/{id}", response_model=ConversationResponse)
async def rename_conversation(
    id: uuid.UUID,
    payload: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Rename a conversation title."""
    conv = await conv_service.rename_conversation(
        db=db,
        conversation_id=id,
        user_id=current_user.id,
        new_title=payload.title
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )
    await db.commit()
    full_conv = await conv_service.get_conversation(db, conv.id, current_user.id)
    return full_conv


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Soft delete a conversation session."""
    success = await conv_service.delete_conversation(
        db=db,
        conversation_id=id,
        user_id=current_user.id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )
    await db.commit()
    return


@router.post("/{id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    id: uuid.UUID,
    payload: MessageCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send user message and generate LLM text completion."""
    return await chat_service.send_message(
        db=db,
        conversation_id=id,
        user_id=current_user.id,
        user_content=payload.content,
        background_tasks=background_tasks
    )


@router.get("/{id}/messages", response_model=List[MessageResponse])
async def list_messages(
    id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch paginated message histories for a conversation."""
    conv = await conv_service.get_conversation(db=db, conversation_id=id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )
    return await msg_repo.list_by_conversation(
        db=db,
        conversation_id=id,
        limit=limit,
        offset=offset
    )


@router.get("/{id}/stream")
async def stream_message(
    id: uuid.UUID,
    content: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Initiate a real-time Server-Sent Events (SSE) response stream via GET."""
    conv = await conv_service.get_conversation(db=db, conversation_id=id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )

    async def sse_generator():
        try:
            async for chunk in stream_service.generate_response_stream(
                db=db,
                conversation_id=id,
                user_id=current_user.id,
                user_content=content
            ):
                yield chunk
        except Exception as e:
            logger.error(f"SSE stream error for conversation {id}: {str(e)}")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.post("/{id}/messages/stream")
async def stream_message_post(
    id: uuid.UUID,
    payload: MessageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Initiate a real-time Server-Sent Events (SSE) response stream via POST."""
    conv = await conv_service.get_conversation(db=db, conversation_id=id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )

    async def sse_generator():
        try:
            async for chunk in stream_service.generate_response_stream(
                db=db,
                conversation_id=id,
                user_id=current_user.id,
                user_content=payload.content,
                request=request
            ):
                yield chunk
        except Exception as e:
            logger.error(f"SSE stream error for conversation {id}: {str(e)}")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.post("/{id}/cancel")
async def cancel_generation(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel any active model response generation for the conversation."""
    conv = await conv_service.get_conversation(db=db, conversation_id=id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )

    # Set cancel signal in Redis
    try:
        await status_service.set_cancelled(id)
    except Exception as e:
        logger.warning(f"Failed to set cancelled status in Redis: {str(e)}")

    # Clear generation lock
    lock_key = f"lock:conversation:{id}:generation"
    try:
        await redis_client.delete(lock_key)
    except Exception as e:
        logger.warning(f"Failed to release Redis lock: {str(e)}")

    # Find PENDING or STREAMING messages and mark as CANCELLED
    all_msgs = await msg_repo.list_by_conversation(db, id)
    for m in all_msgs:
        if m.status in ("PENDING", "STREAMING"):
            m.status = "CANCELLED"
            m.finish_reason = "CANCELLED"
            db.add(m)
    await db.commit()

    return {"status": "CANCELLED"}


@router.get("/{id}/status")
async def get_generation_status(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve real-time generation status attributes from Redis."""
    conv = await conv_service.get_conversation(db=db, conversation_id=id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )

    try:
        return await status_service.get_status(id)
    except Exception as e:
        logger.error(f"Failed to get Redis generation status: {str(e)}")
        return {
            "status": "IDLE",
            "provider": "gemini",
            "elapsed_ms": 0,
            "tokens_generated": 0
        }


@router.get("/{id}/export")
async def export_conversation(
    id: uuid.UUID,
    format: str = Query("txt"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export conversation message histories to multiple files format types."""
    conv = await conv_service.get_conversation(db=db, conversation_id=id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )

    try:
        file_bytes, media_type, filename = await export_service.get_export_data(
            db=db,
            conversation_id=id,
            user_id=current_user.id,
            export_format=format
        )
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# --- Message-Level Endpoints Router (/api/v1/messages) ---

@msg_router.post("/{message_id}/regenerate", response_model=MessageResponse)
async def regenerate_message(
    message_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    stream: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deactivate assistant message and trigger regenerated model response."""
    msg = await msg_repo.get_by_id(db, message_id)
    if not msg or msg.role != "assistant":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant message not found."
        )

    conv = await conv_service.get_conversation(db=db, conversation_id=msg.conversation_id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )

    # Fetch chronological history and get preceding active user message
    all_msgs = await msg_repo.list_by_conversation(db, msg.conversation_id)
    prior_active = [m for m in all_msgs if m.is_active and m.created_at < msg.created_at]
    user_msgs = [m for m in prior_active if m.role == "user"]
    if not user_msgs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No preceding active user message to regenerate from."
        )
    last_user_msg = user_msgs[-1]

    # Invalidate (deactivate) this message and all messages chronologically after it
    msg.is_active = False
    db.add(msg)
    for m in all_msgs:
        if m.created_at > msg.created_at:
            m.is_active = False
            db.add(m)
    await db.commit()

    new_version = msg.version + 1
    new_retry = msg.retry_count + 1

    # Regenerate response
    new_msg = await chat_service.send_message(
        db=db,
        conversation_id=msg.conversation_id,
        user_id=current_user.id,
        user_content=last_user_msg.content,
        background_tasks=background_tasks
    )

    # Update versioning meta parameters
    new_msg.version = new_version
    new_msg.retry_count = new_retry
    new_msg.parent_message_id = msg.id
    await db.commit()
    
    # Reload from DB to return accurate schema
    return await msg_repo.get_by_id(db, new_msg.id)


@msg_router.put("/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: uuid.UUID,
    payload: MessageCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Edit user message content, invalidating and regenerating subsequent thread chains."""
    msg = await msg_repo.get_by_id(db, message_id)
    if not msg or msg.role != "user":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User message not found."
        )

    conv = await conv_service.get_conversation(db=db, conversation_id=msg.conversation_id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )

    # Deactivate current message and subsequent messages
    all_msgs = await msg_repo.list_by_conversation(db, msg.conversation_id)
    msg.is_active = False
    db.add(msg)
    for m in all_msgs:
        if m.created_at > msg.created_at:
            m.is_active = False
            db.add(m)
    await db.commit()

    # Create new user message version
    new_user_msg = await msg_repo.create(
        db=db,
        conversation_id=msg.conversation_id,
        role="user",
        content=payload.content,
        status="COMPLETED",
        edited=True,
        version=msg.version + 1,
        parent_message_id=msg.id
    )
    await db.commit()

    # Generate assistant follow-up response
    assistant_msg = await chat_service.send_message(
        db=db,
        conversation_id=msg.conversation_id,
        user_id=current_user.id,
        user_content=payload.content,
        background_tasks=background_tasks
    )
    return assistant_msg


@msg_router.post("/{message_id}/feedback")
async def set_message_feedback(
    message_id: uuid.UUID,
    payload: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit thumbs, rating, stars, and report reactions feedback for assistant messages."""
    msg = await msg_repo.get_by_id(db, message_id)
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found."
        )

    conv = await conv_service.get_conversation(db=db, conversation_id=msg.conversation_id, user_id=current_user.id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or unauthorized access."
        )

    from sqlalchemy import select
    from app.models.conversation import MessageFeedback

    # Check if feedback exists
    stmt = select(MessageFeedback).where(MessageFeedback.message_id == message_id)
    res = await db.execute(stmt)
    fb = res.scalars().first()

    rating_val = payload.rating.upper()
    if rating_val == "NONE":
        if fb:
            await db.delete(fb)
            await db.commit()
        return {"status": "deleted"}

    if rating_val not in ("LIKE", "DISLIKE", "SAVE", "REPORT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid rating value. Must be LIKE, DISLIKE, SAVE, REPORT, or none."
        )

    if fb:
        fb.rating = rating_val
    else:
        fb = MessageFeedback(
            message_id=message_id,
            rating=rating_val
        )
        db.add(fb)

    await db.commit()
    return {"status": "saved", "rating": rating_val}
