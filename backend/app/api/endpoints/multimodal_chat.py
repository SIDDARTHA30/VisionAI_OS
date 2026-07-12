"""
Module 3 — Multimodal Chat Endpoint
Extends conversation messaging to support image/file attachments alongside text.

Route:
    POST /api/v1/conversations/{conversation_id}/messages/multimodal

Same response schema as existing /messages endpoint — zero breaking changes to frontend.
"""
import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.conversation import MessageResponse
from app.schemas.file_asset import MultimodalMessageCreate
from app.services.multimodal.multimodal_chat_service import MultimodalChatService

logger = logging.getLogger(__name__)
router = APIRouter()

multimodal_chat_service = MultimodalChatService()


@router.post(
    "/{conversation_id}/messages/multimodal",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED
)
async def send_multimodal_message(
    conversation_id: uuid.UUID,
    payload: MultimodalMessageCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a chat message with one or more file attachments.

    The message combines text content with pre-uploaded FileAssets (by UUID).
    All referenced files must have status=READY (upload to Gemini completed).

    The assistant's response considers both the conversation history and
    the visual/document content of the attached files.

    Response schema is identical to the standard POST /messages endpoint.
    """
    assistant_msg = await multimodal_chat_service.send_multimodal_message(
        db=db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        user_content=payload.content,
        file_ids=payload.file_ids,
        background_tasks=background_tasks,
    )
    return assistant_msg
