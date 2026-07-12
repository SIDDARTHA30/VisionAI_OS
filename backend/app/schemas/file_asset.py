"""
Module 3 — Pydantic schemas for FileAsset API responses and requests.
"""
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class FileAssetResponse(BaseModel):
    """Full file asset metadata returned after upload or fetch."""
    id: uuid.UUID
    user_id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    status: str
    gemini_file_uri: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FileUploadResponse(BaseModel):
    """Immediate response returned after a file upload request completes."""
    file_id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    status: str
    message: str = "File uploaded successfully. Gemini processing in progress."


class FileListResponse(BaseModel):
    """Paginated list of file assets for the current user."""
    files: List[FileAssetResponse]
    total: int


# ─── Vision ────────────────────────────────────────────────────────────────────

class VisionAnalyzeRequest(BaseModel):
    file_id: uuid.UUID
    prompt: Optional[str] = Field(None, description="Custom prompt to guide analysis")


class VisionAskRequest(BaseModel):
    file_id: uuid.UUID
    question: str = Field(..., min_length=1)


class VisionResponse(BaseModel):
    file_id: uuid.UUID
    result: str
    operation: str


class VisionDetectResponse(BaseModel):
    file_id: uuid.UUID
    objects: List[dict]
    raw: str


# ─── Documents ─────────────────────────────────────────────────────────────────

class DocumentRequest(BaseModel):
    file_id: uuid.UUID


class DocumentAskRequest(BaseModel):
    file_id: uuid.UUID
    question: str = Field(..., min_length=1)


class DocumentResponse(BaseModel):
    file_id: uuid.UUID
    result: str
    operation: str


class DocumentTablesResponse(BaseModel):
    file_id: uuid.UUID
    tables: List[dict]
    raw: str


# ─── Speech ────────────────────────────────────────────────────────────────────

class TranscribeRequest(BaseModel):
    file_id: uuid.UUID
    language: Optional[str] = Field(None, description="BCP-47 language code, e.g. 'en', 'fr'")


class TranslateRequest(BaseModel):
    file_id: uuid.UUID
    target_language: str = Field(..., description="Target language name, e.g. 'French'")


class TranscriptResponse(BaseModel):
    file_id: uuid.UUID
    transcript: str
    language: Optional[str] = None
    operation: str


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    voice: Optional[str] = Field(None, description="Voice name e.g. Kore, Puck, Charon")


class VoiceInfo(BaseModel):
    name: str
    description: str


# ─── Multimodal Chat ───────────────────────────────────────────────────────────

class MultimodalMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Text content of the message")
    file_ids: List[uuid.UUID] = Field(default_factory=list, description="UUIDs of pre-uploaded FileAssets")
