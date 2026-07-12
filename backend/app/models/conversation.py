import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import relationship
from app.db.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    message_count = Column(Integer, default=0, nullable=False)
    last_message_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Conversation Branching columns
    parent_conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    branch_name = Column(String(100), nullable=True)
    branch_depth = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User", back_populates="conversations_new")
    settings = relationship("ConversationSetting", back_populates="conversation", uselist=False, cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    token_usages = relationship("TokenUsage", back_populates="conversation", cascade="all, delete-orphan")


class ConversationSetting(Base):
    __tablename__ = "conversation_settings"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), unique=True, nullable=False)
    model = Column(String(100), nullable=False)
    temperature = Column(Float, default=0.7, nullable=False)
    max_tokens = Column(Integer, default=2048, nullable=False)
    language = Column(String(50), default="en", nullable=False)
    system_prompt = Column(Text, nullable=True)
    stream_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="settings")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    status = Column(String(50), default="COMPLETED", nullable=False)  # PENDING, STREAMING, COMPLETED, FAILED, CANCELLED
    response_time_ms = Column(Integer, nullable=True)
    finish_reason = Column(String(100), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    is_streamed = Column(Boolean, default=False, nullable=False)
    edited = Column(Boolean, default=False, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Versioning columns
    parent_message_id = Column(Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    token_usage = relationship("TokenUsage", back_populates="message", uselist=False, cascade="all, delete-orphan")
    feedback = relationship("MessageFeedback", back_populates="message", uselist=False, cascade="all, delete-orphan")


class MessageFeedback(Base):
    __tablename__ = "message_feedback"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False)
    rating = Column(String(50), nullable=False)  # LIKE, DISLIKE, SAVE, REPORT
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    message = relationship("Message", back_populates="feedback")


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), unique=True, nullable=False)
    provider = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    estimated_cost = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="token_usages")
    message = relationship("Message", back_populates="token_usage")
