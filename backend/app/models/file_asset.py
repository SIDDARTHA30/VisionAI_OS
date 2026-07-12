"""
Module 3 — Multimodal Intelligence Layer
Database models for uploaded file assets and their association to messages.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import relationship

from app.db.database import Base


class FileAsset(Base):
    """
    Registry of every file uploaded by a user.

    Lifecycle:
        PENDING  → file saved locally, Gemini upload in progress
        READY    → Gemini Files API returned an active URI
        EXPIRED  → Gemini URI has expired (48-hour TTL)
        FAILED   → upload or processing failed
    """
    __tablename__ = "file_assets"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Original file metadata
    original_filename = Column(String(512), nullable=False)
    stored_path = Column(Text, nullable=False)           # Absolute path on local disk
    mime_type = Column(String(255), nullable=False)
    size_bytes = Column(Integer, nullable=False)

    # Gemini Files API reference
    gemini_file_uri = Column(Text, nullable=True)        # e.g. https://generativelanguage.googleapis.com/v1beta/files/xxx
    gemini_file_name = Column(String(512), nullable=True)  # e.g. files/abc123 (used to re-fetch)

    # Status
    status = Column(String(50), default="PENDING", nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Gemini TTL: 48 hours from upload

    # Relationships
    attachments = relationship("MessageAttachment", back_populates="file_asset", cascade="all, delete-orphan")


class MessageAttachment(Base):
    """
    Junction table linking a Message to one or more FileAssets.
    Enables multimodal chat where a single message can reference multiple files.
    """
    __tablename__ = "message_attachments"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    file_asset_id = Column(Uuid(as_uuid=True), ForeignKey("file_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    file_asset = relationship("FileAsset", back_populates="attachments")
