"""
Module 3 — Vision API Endpoints
Image analysis, OCR, captioning, object detection, visual Q&A, and chart interpretation.

Routes:
    POST /api/v1/vision/analyze   — General comprehensive image analysis
    POST /api/v1/vision/ocr       — Extract all text from image
    POST /api/v1/vision/caption   — Generate a concise image caption
    POST /api/v1/vision/detect    — Detect and list all objects in image
    POST /api/v1/vision/ask       — Answer a specific question about the image
    POST /api/v1/vision/chart     — Interpret charts, graphs, and tables
"""
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.file_asset import (
    VisionAnalyzeRequest,
    VisionAskRequest,
    VisionDetectResponse,
    VisionResponse,
)
from app.services.multimodal.vision_service import VisionService

logger = logging.getLogger(__name__)
router = APIRouter()

vision_service = VisionService()


@router.post("/analyze", response_model=VisionResponse, status_code=status.HTTP_200_OK)
async def analyze_image(
    payload: VisionAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Perform a comprehensive analysis of an uploaded image.
    Describes objects, scene, colors, composition, and context.
    Optionally accepts a custom prompt to guide the analysis.
    """
    result = await vision_service.analyze_image(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
        custom_prompt=payload.prompt,
    )
    return VisionResponse(file_id=payload.file_id, result=result, operation="analyze")


@router.post("/ocr", response_model=VisionResponse, status_code=status.HTTP_200_OK)
async def extract_text_ocr(
    payload: VisionAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Extract all text visible in the image using Gemini's native OCR.
    Works for printed text, handwriting, screenshots, signs, and scanned documents.
    Preserves original line breaks and paragraph structure.
    """
    result = await vision_service.extract_text_ocr(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
    )
    return VisionResponse(file_id=payload.file_id, result=result, operation="ocr")


@router.post("/caption", response_model=VisionResponse, status_code=status.HTTP_200_OK)
async def generate_caption(
    payload: VisionAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a single concise, descriptive caption for the image.
    Suitable for alt text, image metadata, or document annotations.
    """
    result = await vision_service.generate_caption(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
    )
    return VisionResponse(file_id=payload.file_id, result=result, operation="caption")


@router.post("/detect", response_model=VisionDetectResponse, status_code=status.HTTP_200_OK)
async def detect_objects(
    payload: VisionAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Detect and identify all distinct objects, people, animals, and items in the image.
    Returns a structured JSON list with confidence levels and spatial descriptions.
    """
    result = await vision_service.detect_objects(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
    )
    return VisionDetectResponse(
        file_id=payload.file_id,
        objects=result.get("objects", []),
        raw=result.get("raw", ""),
    )


@router.post("/ask", response_model=VisionResponse, status_code=status.HTTP_200_OK)
async def answer_visual_question(
    payload: VisionAskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Answer a specific question about the content of an image.
    Ideal for grounding questions in visual evidence (e.g. 'What brand is shown?').
    """
    result = await vision_service.answer_question(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
        question=payload.question,
    )
    return VisionResponse(file_id=payload.file_id, result=result, operation="ask")


@router.post("/chart", response_model=VisionResponse, status_code=status.HTTP_200_OK)
async def analyze_chart(
    payload: VisionAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Interpret charts, graphs, tables, and data visualizations in the image.
    Extracts data points, trends, axes, and key insights from visual data representations.
    """
    result = await vision_service.analyze_chart(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
    )
    return VisionResponse(file_id=payload.file_id, result=result, operation="chart")
