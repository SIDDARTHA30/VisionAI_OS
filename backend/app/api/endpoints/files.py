"""
Module 3 — Files API Endpoints
Handles multipart file upload, listing, retrieval, and deletion.

Routes:
    POST   /api/v1/files/upload      — Upload a new file
    GET    /api/v1/files/            — List user's files
    GET    /api/v1/files/{file_id}   — Get file metadata
    DELETE /api/v1/files/{file_id}   — Delete file (local + Gemini)
"""
import uuid
import logging
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.file_asset import FileAssetResponse, FileUploadResponse
from app.services.multimodal.file_service import FileService
from app.repositories.file_repository import FileRepository

logger = logging.getLogger(__name__)
router = APIRouter()

file_service = FileService()
file_repo = FileRepository()


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a file for multimodal processing.

    Accepts: images (JPEG, PNG, GIF, WebP), audio (MP3, WAV, WebM, OGG, AAC, FLAC),
             documents (PDF, TXT, CSV, DOCX, XLSX, PPTX, Markdown).

    File size limits: 50MB for images/audio, 200MB for documents.

    Returns immediately with status=PENDING. The file is uploaded to Gemini Files API
    in the background. Poll GET /files/{file_id} until status=READY before use.
    """
    asset = await file_service.upload(
        db=db,
        upload_file=file,
        user_id=current_user.id,
        background_tasks=background_tasks,
    )
    return FileUploadResponse(
        file_id=asset.id,
        original_filename=asset.original_filename,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        status=asset.status,
        message="File received. Gemini processing started in background. Poll until status=READY."
    )


@router.get("/", response_model=List[FileAssetResponse])
async def list_files(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all files uploaded by the authenticated user, most recent first."""
    files = await file_repo.list_by_user(
        db=db,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return files


@router.get("/{file_id}", response_model=FileAssetResponse)
async def get_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve metadata for a specific file.
    Poll this endpoint until status changes from PENDING to READY before using the file.
    """
    asset = await file_repo.get_by_id_and_user(db, file_id, current_user.id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found or does not belong to you."
        )
    return asset


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a file from local storage, Gemini Files API, and the database.
    This action is irreversible.
    """
    success = await file_service.delete_file(
        db=db,
        file_id=file_id,
        user_id=current_user.id,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found or does not belong to you."
        )
    return
