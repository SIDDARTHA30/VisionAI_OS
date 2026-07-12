"""
Module 3 — FileRepository: Database access layer for FileAsset model.
Follows the same pattern as MessageRepository and ConversationRepository.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_asset import FileAsset, MessageAttachment

logger = logging.getLogger(__name__)


class FileRepository:
    """Repository managing all database operations for FileAsset and MessageAttachment."""

    # ─── FileAsset CRUD ────────────────────────────────────────────────────────

    async def create(
        self,
        db: AsyncSession,
        user_id: int,
        original_filename: str,
        stored_path: str,
        mime_type: str,
        size_bytes: int,
    ) -> FileAsset:
        """Insert a new FileAsset record in PENDING state."""
        asset = FileAsset(
            user_id=user_id,
            original_filename=original_filename,
            stored_path=stored_path,
            mime_type=mime_type,
            size_bytes=size_bytes,
            status="PENDING",
        )
        db.add(asset)
        await db.flush()
        logger.debug(f"FileAsset created: id={asset.id}, user={user_id}, mime={mime_type}")
        return asset

    async def get_by_id(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
    ) -> Optional[FileAsset]:
        """Fetch a FileAsset by its UUID."""
        stmt = select(FileAsset).where(FileAsset.id == file_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_by_id_and_user(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> Optional[FileAsset]:
        """Fetch a FileAsset verifying ownership."""
        stmt = select(FileAsset).where(
            FileAsset.id == file_id,
            FileAsset.user_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_by_user(
        self,
        db: AsyncSession,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[FileAsset]:
        """List all file assets for a user, most recent first."""
        stmt = (
            select(FileAsset)
            .where(FileAsset.user_id == user_id)
            .order_by(FileAsset.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_gemini_uri(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        gemini_file_uri: str,
        gemini_file_name: str,
    ) -> Optional[FileAsset]:
        """Mark the asset as READY and store the Gemini Files API URI and name."""
        asset = await self.get_by_id(db, file_id)
        if not asset:
            return None
        asset.gemini_file_uri = gemini_file_uri
        asset.gemini_file_name = gemini_file_name
        asset.status = "READY"
        # Gemini Files API guarantees 48-hour TTL from upload time
        asset.expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
        db.add(asset)
        await db.flush()
        return asset

    async def mark_failed(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> Optional[FileAsset]:
        """Transition a FileAsset to FAILED state."""
        asset = await self.get_by_id(db, file_id)
        if not asset:
            return None
        asset.status = "FAILED"
        db.add(asset)
        await db.flush()
        logger.warning(f"FileAsset marked FAILED: id={file_id}, reason={reason}")
        return asset

    async def mark_expired(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
    ) -> Optional[FileAsset]:
        """Mark a FileAsset as EXPIRED when the Gemini URI has lapsed."""
        asset = await self.get_by_id(db, file_id)
        if not asset:
            return None
        asset.status = "EXPIRED"
        db.add(asset)
        await db.flush()
        return asset

    async def delete(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> bool:
        """Hard delete a FileAsset (caller is responsible for removing local file)."""
        asset = await self.get_by_id_and_user(db, file_id, user_id)
        if not asset:
            return False
        await db.delete(asset)
        await db.flush()
        return True

    # ─── MessageAttachment operations ─────────────────────────────────────────

    async def attach_to_message(
        self,
        db: AsyncSession,
        message_id: uuid.UUID,
        file_asset_id: uuid.UUID,
    ) -> MessageAttachment:
        """Create a join record linking a Message to a FileAsset."""
        attachment = MessageAttachment(
            message_id=message_id,
            file_asset_id=file_asset_id,
        )
        db.add(attachment)
        await db.flush()
        return attachment

    async def get_attachments_for_message(
        self,
        db: AsyncSession,
        message_id: uuid.UUID,
    ) -> List[FileAsset]:
        """Return all FileAssets attached to a given message."""
        stmt = (
            select(FileAsset)
            .join(MessageAttachment, MessageAttachment.file_asset_id == FileAsset.id)
            .where(MessageAttachment.message_id == message_id)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
