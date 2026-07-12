"""
Module 3 — DocumentService: Document understanding for PDF, DOCX, TXT, CSV, XLSX, PPTX.

Strategy: All supported formats are uploaded directly to the Gemini Files API.
Gemini natively reads PDF (including scanned/OCR), DOCX, TXT, CSV, etc.
No third-party parsing libraries required for the core flow.
"""
import json
import logging
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_asset import FileAsset
from app.repositories.file_repository import FileRepository
from app.providers.provider_registry import provider_registry
from app.core.ai_config import ai_config

logger = logging.getLogger(__name__)

# MIME types treated as documents (not images or audio)
DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/msword",
}


class DocumentService:
    """
    Document understanding operations: summarization, extraction, Q&A, and table parsing.
    Delegates all LLM calls to GeminiProvider.analyze_file().
    """

    def __init__(self):
        self.file_repo = FileRepository()

    # ─── Private helpers ──────────────────────────────────────────────────────

    async def _get_ready_document(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> FileAsset:
        """Fetch and validate a READY document FileAsset."""
        asset = await self.file_repo.get_by_id_and_user(db, file_id, user_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File {file_id} not found or does not belong to you."
            )
        if asset.status == "PENDING":
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail="File is still being processed by Gemini. Please retry in a few seconds."
            )
        if asset.status == "EXPIRED":
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="File has expired (Gemini 48-hour TTL). Please re-upload."
            )
        if asset.status == "FAILED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File processing failed. Please re-upload."
            )
        # Accept both explicit document types and plain text/image embedded in docs
        if asset.mime_type not in DOCUMENT_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{asset.mime_type}' is not a supported document format. "
                       f"Supported: PDF, TXT, CSV, DOCX, XLSX, PPTX, Markdown."
            )
        return asset

    async def _call_provider(
        self,
        gemini_file_name: str,
        mime_type: str,
        prompt: str,
    ) -> str:
        """Route to GeminiProvider.analyze_file()."""
        provider = provider_registry.get("gemini")
        return await provider.analyze_file(
            gemini_file_name=gemini_file_name,
            mime_type=mime_type,
            prompt=prompt,
            settings_dict={"model": ai_config.GEMINI_MODEL},
        )

    # ─── Public operations ────────────────────────────────────────────────────

    async def summarize_document(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> str:
        """
        Generate an executive summary of the document.
        Covers main topics, key findings, conclusions, and action items.
        """
        asset = await self._get_ready_document(db, file_id, user_id)
        prompt = (
            "Please provide a comprehensive executive summary of this document. Include:\n"
            "1. Main topics and purpose of the document.\n"
            "2. Key findings, arguments, or data points.\n"
            "3. Important conclusions or recommendations.\n"
            "4. Any action items or next steps mentioned.\n"
            "Format the summary with clear sections and bullet points where appropriate."
        )
        return await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)

    async def extract_text(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> str:
        """
        Extract the full text content from the document, preserving structure.
        For PDFs (including scanned), Gemini performs native OCR.
        """
        asset = await self._get_ready_document(db, file_id, user_id)
        prompt = (
            "Extract all text content from this document verbatim. "
            "Preserve the document structure including headings, paragraphs, lists, and tables. "
            "For tables, format them in a readable way using plain text. "
            "Include all pages and sections."
        )
        return await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)

    async def answer_question(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
        question: str,
    ) -> dict:
        """
        Answer a specific question about the document content.
        Returns the answer along with page/section references where applicable.
        """
        asset = await self._get_ready_document(db, file_id, user_id)
        prompt = (
            f"Based on the content of this document, please answer the following question:\n\n"
            f"Question: {question}\n\n"
            f"Provide:\n"
            f"1. A clear, accurate answer.\n"
            f"2. Reference the specific page number or section where you found this information (if applicable).\n"
            f"3. Quote the relevant text directly if it helps clarify the answer.\n"
            f"If the answer is not found in the document, clearly state that."
        )
        answer = await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)
        return {"answer": answer, "question": question}

    async def extract_tables(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> dict:
        """
        Extract all tables from the document as structured JSON.
        Returns a list of tables, each with headers and rows.
        """
        asset = await self._get_ready_document(db, file_id, user_id)
        prompt = (
            "Extract all tables from this document and return them as valid JSON. "
            "Use this exact structure: "
            '{"tables": [{"title": "table title or empty string", "headers": ["col1", "col2"], "rows": [["val1", "val2"]]}]}. '
            "If no tables are found, return: {\"tables\": []}. "
            "Only return the JSON object, no additional text."
        )
        raw = await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)
        try:
            clean = raw.strip()
            if "```" in clean:
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            parsed = json.loads(clean.strip())
            return {"tables": parsed.get("tables", []), "raw": raw}
        except json.JSONDecodeError:
            logger.warning(f"Table extraction response was not valid JSON for file {file_id}")
            return {"tables": [], "raw": raw}
