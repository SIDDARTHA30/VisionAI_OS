"""
Module 3 — FileService: Handles file ingestion, MIME validation, local storage,
and asynchronous upload to the Gemini Files API.

Storage strategy: Local Docker volume mounted at /app/uploads (production-upgradeable to S3/GCS).
File size cap: 50 MB for images/audio, 200 MB for documents.
"""
import os
import uuid
import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.file_asset import FileAsset
from app.repositories.file_repository import FileRepository

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

ALLOWED_MIME_TYPES: dict[str, int] = {
    # Images — 50 MB cap
    "image/jpeg": 50,
    "image/png": 50,
    "image/gif": 50,
    "image/webp": 50,
    "image/bmp": 50,
    # Audio — 50 MB cap
    "audio/mpeg": 50,
    "audio/mp3": 50,
    "audio/wav": 50,
    "audio/webm": 50,
    "audio/ogg": 50,
    "audio/aac": 50,
    "audio/flac": 50,
    "audio/x-m4a": 50,
    "audio/mp4": 50,
    # Documents — 200 MB cap
    "application/pdf": 200,
    "text/plain": 200,
    "text/csv": 200,
    "text/markdown": 200,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": 200,   # docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": 200,         # xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": 200, # pptx
    "application/msword": 200,
}

IMAGE_MIME_TYPES = {k for k in ALLOWED_MIME_TYPES if k.startswith("image/")}
AUDIO_MIME_TYPES = {k for k in ALLOWED_MIME_TYPES if k.startswith("audio/")}


class FileService:
    """
    Orchestrates the full file upload pipeline:
    1. Validate MIME type and file size.
    2. Save bytes to local disk under /app/uploads/{user_id}/{file_uuid}/.
    3. Persist a PENDING FileAsset record to the database.
    4. Enqueue a background task to upload the file to the Gemini Files API
       and update the record to READY.
    """

    def __init__(self):
        self.file_repo = FileRepository()

    # ─── Public API ───────────────────────────────────────────────────────────

    async def upload(
        self,
        db: AsyncSession,
        upload_file: UploadFile,
        user_id: int,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> FileAsset:
        """
        Main entry point. Validates, stores, persists, and enqueues Gemini upload.
        Returns the FileAsset record (status=PENDING until background task completes).
        """
        # 1. Detect MIME type
        mime_type = self._detect_mime(upload_file)

        # 2. Validate MIME is allowed
        if mime_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File type '{mime_type}' is not supported. "
                       f"Allowed types: images (JPEG, PNG, GIF, WebP), "
                       f"audio (MP3, WAV, WebM, OGG, AAC, FLAC), "
                       f"documents (PDF, TXT, CSV, DOCX, XLSX, PPTX)."
            )

        # 3. Read file and validate size
        file_bytes = await upload_file.read()
        size_bytes = len(file_bytes)
        max_mb = ALLOWED_MIME_TYPES[mime_type]
        max_bytes = max_mb * 1024 * 1024

        if size_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size {size_bytes // (1024*1024)}MB exceeds the "
                       f"{max_mb}MB limit for {mime_type} files."
            )

        if size_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty."
            )

        # 4. Save to local disk
        file_uuid = uuid.uuid4()
        stored_path = self._save_to_disk(
            file_bytes=file_bytes,
            user_id=user_id,
            file_uuid=file_uuid,
            original_filename=upload_file.filename or "upload",
        )

        # 5. Persist PENDING record to DB
        asset = await self.file_repo.create(
            db=db,
            user_id=user_id,
            original_filename=upload_file.filename or "upload",
            stored_path=stored_path,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
        await db.commit()

        logger.info(
            f"File stored locally: id={asset.id}, user={user_id}, "
            f"mime={mime_type}, size={size_bytes}B, path={stored_path}"
        )

        # 6. Enqueue background upload to Gemini Files API
        #
        # IMPORTANT: FastAPI BackgroundTasks natively supports async functions.
        # We register _upload_to_gemini_async directly so it runs in the SAME
        # event loop as the application — avoiding the "Future attached to a
        # different loop" error that occurs when a sync wrapper creates a new loop.
        if background_tasks:
            background_tasks.add_task(
                self._upload_to_gemini_async,
                asset_id=asset.id,
                stored_path=stored_path,
                mime_type=mime_type,
                original_filename=upload_file.filename or "upload",
            )
        else:
            # Direct await fallback used in tests or non-background contexts.
            await self._upload_to_gemini_async(
                asset_id=asset.id,
                stored_path=stored_path,
                mime_type=mime_type,
                original_filename=upload_file.filename or "upload",
            )

        return asset

    async def delete_file(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> bool:
        """
        Delete a file from local disk, Gemini Files API, and the database.
        Returns True on success, False if not found.
        """
        asset = await self.file_repo.get_by_id_and_user(db, file_id, user_id)
        if not asset:
            return False

        # Remove local file
        self._delete_local_file(asset.stored_path)

        # Remove from Gemini Files API (best effort)
        if asset.gemini_file_name:
            self._delete_from_gemini(asset.gemini_file_name)

        # Remove from DB
        await self.file_repo.delete(db, file_id, user_id)
        await db.commit()
        return True

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _detect_mime(self, upload_file: UploadFile) -> str:
        """Determine MIME type from Content-Type header, falling back to filename extension."""
        content_type = upload_file.content_type or ""
        # Strip charset suffix e.g. "text/plain; charset=utf-8"
        mime = content_type.split(";")[0].strip().lower()
        if mime and mime != "application/octet-stream":
            return mime
        # Fallback: guess from filename extension
        guessed, _ = mimetypes.guess_type(upload_file.filename or "")
        if guessed:
            return guessed.lower()
        return "application/octet-stream"

    def _save_to_disk(
        self,
        file_bytes: bytes,
        user_id: int,
        file_uuid: uuid.UUID,
        original_filename: str,
    ) -> str:
        """Save uploaded bytes to the local upload volume and return the absolute path."""
        upload_root = getattr(settings, "UPLOAD_DIR", "/app/uploads")
        dest_dir = Path(upload_root) / str(user_id) / str(file_uuid)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / original_filename
        dest_path.write_bytes(file_bytes)
        return str(dest_path)

    def _delete_local_file(self, stored_path: str) -> None:
        """Remove a file and its parent directory from local disk."""
        try:
            path = Path(stored_path)
            if path.exists():
                path.unlink()
            # Remove the UUID directory if empty
            if path.parent.exists() and not any(path.parent.iterdir()):
                path.parent.rmdir()
        except Exception as e:
            logger.warning(f"Failed to delete local file '{stored_path}': {e}")

    async def _upload_to_gemini_async(
        self,
        asset_id: uuid.UUID,
        stored_path: str,
        mime_type: str,
        original_filename: str,
    ) -> None:
        """
        Upload the file to the Gemini Files API and update the DB record.

        This is registered directly as a FastAPI BackgroundTask (async).
        It runs in the SAME event loop as the application, so AsyncSessionLocal()
        uses the same engine connection pool — no cross-loop Future errors.

        A fresh database session is created here (never reuse the request session
        across the background task boundary).
        """
        import asyncio
        from google import genai
        from app.db.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            try:
                client = genai.Client(api_key=settings.GOOGLE_API_KEY or "MOCK_KEY")

                # The google-genai SDK's files.upload() is synchronous.
                # Run it in the default thread pool so it doesn't block the event loop.
                # get_running_loop() is correct here — we are inside an async function.
                loop = asyncio.get_running_loop()
                gemini_file = await loop.run_in_executor(
                    None,
                    lambda: client.files.upload(
                        file=stored_path,
                        config={"mime_type": mime_type, "display_name": original_filename}
                    )
                )

                logger.info(
                    f"Gemini upload complete: asset={asset_id}, "
                    f"name={gemini_file.name}, uri={gemini_file.uri}"
                )

                # Update the DB record to READY with the Gemini file reference
                await self.file_repo.update_gemini_uri(
                    db=db,
                    file_id=asset_id,
                    gemini_file_uri=gemini_file.uri,
                    gemini_file_name=gemini_file.name,
                )
                await db.commit()

                logger.info(f"FileAsset {asset_id} status → READY")

            except Exception as e:
                logger.error(f"Gemini Files API upload failed for asset {asset_id}: {e}")
                try:
                    await self.file_repo.mark_failed(db=db, file_id=asset_id, reason=str(e))
                    await db.commit()
                except Exception as db_err:
                    logger.error(f"Also failed to mark asset {asset_id} as FAILED: {db_err}")

    def _delete_from_gemini(self, gemini_file_name: str) -> None:
        """Best-effort delete from Gemini Files API."""
        try:
            from google import genai
            client = genai.Client(api_key=settings.GOOGLE_API_KEY or "MOCK_KEY")
            client.files.delete(name=gemini_file_name)
            logger.info(f"Deleted Gemini file: {gemini_file_name}")
        except Exception as e:
            logger.warning(f"Failed to delete Gemini file '{gemini_file_name}': {e}")
