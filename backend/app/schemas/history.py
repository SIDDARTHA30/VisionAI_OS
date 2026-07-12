from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# Conversation Schemas
class ConversationCreate(BaseModel):
    session_id: str = Field(..., max_length=100)
    prompt: str
    response: str


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    session_id: str
    prompt: str
    response: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# User Setting Schemas
class SettingCreate(BaseModel):
    key: str = Field(..., max_length=100)
    value: str = Field(..., max_length=500)


class SettingResponse(BaseModel):
    id: int
    user_id: int
    key: str
    value: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Document Schemas
class DocumentResponse(BaseModel):
    id: int
    user_id: int
    filename: str
    file_path: str
    file_size: int
    mime_type: str
    vector_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# API Key Schemas
class ApiKeyCreate(BaseModel):
    key_name: str = Field(..., max_length=100)
    key_value: str = Field(..., max_length=500)


class ApiKeyResponse(BaseModel):
    id: int
    user_id: int
    key_name: str
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# Activity Log Schemas
class ActivityLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
