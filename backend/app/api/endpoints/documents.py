"""
Module 3 — Documents API Endpoints
Document understanding for PDF, DOCX, TXT, CSV, XLSX, PPTX via Gemini native file support.

Routes:
    POST /api/v1/documents/summarize  — Executive summary
    POST /api/v1/documents/extract    — Full text extraction
    POST /api/v1/documents/ask        — Document Q&A with page references
    POST /api/v1/documents/tables     — Extract tables as structured JSON
"""
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.file_asset import (
    DocumentAskRequest,
    DocumentRequest,
    DocumentResponse,
    DocumentTablesResponse,
)
from app.services.multimodal.document_service import DocumentService

logger = logging.getLogger(__name__)
router = APIRouter()

document_service = DocumentService()


@router.post("/summarize", response_model=DocumentResponse, status_code=status.HTTP_200_OK)
async def summarize_document(
    payload: DocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a comprehensive executive summary of a document.
    Covers main topics, key findings, conclusions, and action items.
    Works with PDF (including scanned), DOCX, TXT, CSV, XLSX, PPTX.
    """
    result = await document_service.summarize_document(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
    )
    return DocumentResponse(file_id=payload.file_id, result=result, operation="summarize")


@router.post("/extract", response_model=DocumentResponse, status_code=status.HTTP_200_OK)
async def extract_text(
    payload: DocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Extract all text content from the document verbatim.
    Preserves headings, paragraphs, lists, and tables.
    For scanned PDFs, Gemini performs native OCR automatically.
    """
    result = await document_service.extract_text(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
    )
    return DocumentResponse(file_id=payload.file_id, result=result, operation="extract")


@router.post("/ask", response_model=DocumentResponse, status_code=status.HTTP_200_OK)
async def ask_document(
    payload: DocumentAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ask a specific question about the document content.
    Returns an accurate answer with page/section references where applicable.
    Ideal for long documents, legal contracts, research papers, and manuals.
    """
    result_data = await document_service.answer_question(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
        question=payload.question,
    )
    return DocumentResponse(
        file_id=payload.file_id,
        result=result_data["answer"],
        operation="ask"
    )


@router.post("/tables", response_model=DocumentTablesResponse, status_code=status.HTTP_200_OK)
async def extract_tables(
    payload: DocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Extract all tables from the document as structured JSON.
    Each table includes title (if found), column headers, and row data.
    Useful for data pipelines, spreadsheet analysis, and report processing.
    """
    result = await document_service.extract_tables(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
    )
    return DocumentTablesResponse(
        file_id=payload.file_id,
        tables=result.get("tables", []),
        raw=result.get("raw", ""),
    )
