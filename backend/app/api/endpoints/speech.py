"""
Module 3 — Speech API Endpoints
Speech-to-Text transcription and Text-to-Speech synthesis.

Routes:
    POST /api/v1/speech/transcribe   — Transcribe audio to text
    POST /api/v1/speech/translate    — Transcribe + translate audio
    POST /api/v1/speech/synthesize   — Convert text to WAV speech audio
    GET  /api/v1/speech/voices       — List all available TTS voices
"""
import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.file_asset import (
    SynthesizeRequest,
    TranscribeRequest,
    TranscriptResponse,
    TranslateRequest,
    VoiceInfo,
)
from app.services.multimodal.speech_service import SpeechService
from app.services.multimodal.tts_service import TTSService
from typing import List

logger = logging.getLogger(__name__)
router = APIRouter()

speech_service = SpeechService()
tts_service = TTSService()


@router.post("/transcribe", response_model=TranscriptResponse, status_code=status.HTTP_200_OK)
async def transcribe_audio(
    payload: TranscribeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Transcribe an uploaded audio file to text using Gemini's native audio understanding.

    Supported formats: MP3, WAV, WebM (browser MediaRecorder), OGG, AAC, FLAC, M4A.
    Optionally provide a BCP-47 language hint (e.g. 'en', 'fr', 'hi') for better accuracy.
    Preserves punctuation, capitalization, and speaker changes if multiple speakers detected.
    """
    result = await speech_service.transcribe(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
        language=payload.language,
    )
    return TranscriptResponse(
        file_id=payload.file_id,
        transcript=result["transcript"],
        language=result["language"],
        operation="transcribe",
    )


@router.post("/translate", response_model=TranscriptResponse, status_code=status.HTTP_200_OK)
async def translate_audio(
    payload: TranslateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Transcribe audio and translate the content to the specified target language.
    Returns both the original transcript and the translation.

    Example: Upload a French audio file, specify target_language='English'.
    """
    result = await speech_service.translate_audio(
        db=db,
        file_id=payload.file_id,
        user_id=current_user.id,
        target_language=payload.target_language,
    )
    # Return the translation as the primary transcript field for API consistency
    return TranscriptResponse(
        file_id=payload.file_id,
        transcript=result["translation"],
        language=result["target_language"],
        operation="translate",
    )


@router.post("/synthesize", status_code=status.HTTP_200_OK)
async def synthesize_speech(
    payload: SynthesizeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Convert text to speech using the Gemini TTS model.

    Returns a WAV audio file (audio/wav) ready for browser playback.
    Maximum text length: 5000 characters.
    Default voice: Kore. Use GET /voices to see all available voices.
    """
    voice = payload.voice or "Kore"
    wav_bytes = await tts_service.synthesize(
        text=payload.text,
        voice=voice,
    )
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": "attachment; filename=synthesis.wav",
            "Content-Length": str(len(wav_bytes)),
            "X-Voice": voice,
        }
    )


@router.get("/voices", response_model=List[VoiceInfo], status_code=status.HTTP_200_OK)
async def list_voices(
    current_user: User = Depends(get_current_user),
):
    """
    List all available Gemini TTS voices with names and descriptions.
    Pass the voice name to POST /synthesize to select a specific voice.
    """
    return tts_service.list_voices()
