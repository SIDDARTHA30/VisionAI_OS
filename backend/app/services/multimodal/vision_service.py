"""
Module 3 — VisionService: All image understanding operations via Gemini multimodal API.

Each method constructs a structured prompt and calls the provider via the existing
GeminiProvider.analyze_file() interface. No God class — only image-specific logic lives here.
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


class VisionService:
    """
    Provides image analysis capabilities by combining FileAsset metadata
    with structured Gemini prompts. Delegates all LLM calls to the provider registry.
    """

    def __init__(self):
        self.file_repo = FileRepository()

    # ─── Private helpers ──────────────────────────────────────────────────────

    async def _get_ready_image(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> FileAsset:
        """Fetch a READY FileAsset that is an image, raising appropriate HTTP errors."""
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
        if not asset.mime_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{asset.mime_type}' is not an image. "
                       f"Vision endpoints only accept image files."
            )
        return asset

    async def _call_provider(
        self,
        gemini_file_name: str,
        mime_type: str,
        prompt: str,
    ) -> str:
        """Delegate to GeminiProvider.analyze_file with retry logic inherited from the provider."""
        provider = provider_registry.get("gemini")
        return await provider.analyze_file(
            gemini_file_name=gemini_file_name,
            mime_type=mime_type,
            prompt=prompt,
            settings_dict={"model": ai_config.GEMINI_MODEL},
        )

    # ─── Public operations ────────────────────────────────────────────────────

    async def analyze_image(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
        custom_prompt: Optional[str] = None,
    ) -> str:
        """
        Perform a general comprehensive analysis of the image.
        Returns a detailed description covering objects, scene, colors, and context.
        """
        asset = await self._get_ready_image(db, file_id, user_id)
        prompt = custom_prompt or (
            "Analyze this image comprehensively. Describe: "
            "1) What you see (objects, people, text, scenes). "
            "2) Colors, lighting, and composition. "
            "3) Any notable features, anomalies, or details. "
            "4) The overall context or purpose of the image."
        )
        return await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)

    async def extract_text_ocr(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> str:
        """
        Extract all visible text from the image using Gemini's native OCR.
        Returns the raw extracted text, preserving line breaks where possible.
        """
        asset = await self._get_ready_image(db, file_id, user_id)
        prompt = (
            "Extract all text visible in this image. "
            "Preserve the original formatting, including line breaks and paragraph structure. "
            "If there is no text, respond with: 'No text detected in this image.'"
        )
        return await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)

    async def detect_objects(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> dict:
        """
        Detect and list all objects in the image.
        Returns structured JSON: { "objects": [...], "count": N }.
        """
        asset = await self._get_ready_image(db, file_id, user_id)
        prompt = (
            "Identify all distinct objects, people, animals, and items visible in this image. "
            "Return the result as valid JSON with this exact structure: "
            '{"objects": [{"name": "object name", "confidence": "high|medium|low", "location": "description of where in image"}], "count": N}. '
            "Only return the JSON object, no additional text."
        )
        raw = await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)
        try:
            # Extract JSON from response even if wrapped in markdown
            clean = raw.strip()
            if "```" in clean:
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            parsed = json.loads(clean.strip())
            return {"objects": parsed.get("objects", []), "count": parsed.get("count", 0), "raw": raw}
        except json.JSONDecodeError:
            logger.warning(f"Object detection response was not valid JSON for file {file_id}")
            return {"objects": [], "count": 0, "raw": raw}

    async def generate_caption(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> str:
        """
        Generate a single concise caption sentence for the image.
        Suitable for alt text, image descriptions in documents, etc.
        """
        asset = await self._get_ready_image(db, file_id, user_id)
        prompt = (
            "Generate a single concise, descriptive caption for this image. "
            "The caption should be one sentence, 10–25 words, suitable as image alt text. "
            "Do not start with 'This image shows' or 'A photo of'."
        )
        return await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)

    async def answer_question(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
        question: str,
    ) -> str:
        """
        Answer a specific question about the image content (visual Q&A).
        """
        asset = await self._get_ready_image(db, file_id, user_id)
        prompt = (
            f"Please answer the following question about this image:\n\n"
            f"Question: {question}\n\n"
            f"Provide a clear, accurate, and detailed answer based only on what you can see in the image."
        )
        return await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)

    async def analyze_chart(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> str:
        """
        Interpret charts, graphs, tables, and diagrams in the image.
        Returns the data represented, trends, and key insights.
        """
        asset = await self._get_ready_image(db, file_id, user_id)
        prompt = (
            "This image appears to contain a chart, graph, table, or data visualization. "
            "Please: "
            "1) Identify the type of visualization (bar chart, line graph, pie chart, table, etc.). "
            "2) Extract the key data points, labels, axes, and values shown. "
            "3) Summarize the main trends or insights the visualization communicates. "
            "4) List any notable outliers or important data points."
        )
        return await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)
