import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ConversationSettingBase(BaseModel):
    model: str = Field("gemini-1.5-flash", description="AI model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, gt=0)
    language: str = Field("en")
    system_prompt: Optional[str] = None
    stream_enabled: bool = True


class ConversationSettingCreate(ConversationSettingBase):
    pass


class ConversationSettingResponse(ConversationSettingBase):
    id: uuid.UUID
    conversation_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    settings: Optional[ConversationSettingCreate] = None


class ConversationUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class ConversationResponse(BaseModel):
    id: uuid.UUID
    user_id: int
    title: str
    summary: Optional[str] = None
    message_count: int
    last_message_at: datetime
    created_at: datetime
    updated_at: datetime
    settings: Optional[ConversationSettingResponse] = None

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    status: str
    response_time_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    is_streamed: bool
    edited: bool
    retry_count: int
    version: int
    parent_message_id: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenUsageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackCreate(BaseModel):
    rating: str = Field(..., description="LIKE, DISLIKE, SAVE, REPORT, none")
