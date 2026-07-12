"""
Module 3 — SpeechService: Speech-to-Text (transcription and translation) via Gemini Files API.

Strategy: Audio files are uploaded to Gemini Files API as FileAssets.
The READY Gemini URI is passed to generate_content with a transcription prompt.
Supports: MP3, WAV, WebM (browser MediaRecorder), OGG, AAC, FLAC, M4A.
"""
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

AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/webm",
    "audio/ogg",
    "audio/aac",
    "audio/flac",
    "audio/x-m4a",
    "audio/mp4",
}


class SpeechService:
    """
    Speech-to-Text operations using Gemini's native audio understanding.
    All audio processing is done server-side via the Files API — no client-side processing.
    """

    def __init__(self):
        self.file_repo = FileRepository()

    # ─── Private helpers ──────────────────────────────────────────────────────

    async def _get_ready_audio(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> FileAsset:
        """Validate and return a READY audio FileAsset."""
        asset = await self.file_repo.get_by_id_and_user(db, file_id, user_id)
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File {file_id} not found or does not belong to you."
            )
        if asset.status == "PENDING":
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail="Audio file is still being processed by Gemini. Please retry in a few seconds."
            )
        if asset.status == "EXPIRED":
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Audio file has expired (Gemini 48-hour TTL). Please re-upload."
            )
        if asset.status == "FAILED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Audio file processing failed. Please re-upload."
            )
        if asset.mime_type not in AUDIO_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type '{asset.mime_type}' is not a supported audio format. "
                       f"Supported: MP3, WAV, WebM, OGG, AAC, FLAC, M4A."
            )
        return asset

    async def _call_provider(
        self,
        gemini_file_name: str,
        mime_type: str,
        prompt: str,
    ) -> str:
        provider = provider_registry.get("gemini")
        return await provider.analyze_file(
            gemini_file_name=gemini_file_name,
            mime_type=mime_type,
            prompt=prompt,
            settings_dict={"model": ai_config.GEMINI_MODEL},
        )

    # ─── Public operations ────────────────────────────────────────────────────

    async def transcribe(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
        language: Optional[str] = None,
    ) -> dict:
        """
        Transcribe speech to text verbatim.
        Preserves punctuation, speaker pauses, and natural sentence breaks.

        Args:
            language: BCP-47 language hint e.g. 'en', 'fr', 'hi'. Auto-detected if None.

        Returns:
            { "transcript": str, "language": str, "operation": "transcribe" }
        """
        asset = await self._get_ready_audio(db, file_id, user_id)
        lang_hint = f" The audio is in {language}." if language else ""
        prompt = (
            f"Please transcribe this audio recording verbatim.{lang_hint} "
            "Include all spoken words exactly as said. "
            "Use proper punctuation, capitalize sentences, and add paragraph breaks for natural pauses. "
            "If multiple speakers are present, indicate speaker changes with [Speaker 1], [Speaker 2], etc. "
            "If the audio is inaudible or silent, respond with: '[Inaudible or silent audio]'."
        )
        transcript = await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)
        return {
            "transcript": transcript,
            "language": language or "auto-detected",
            "operation": "transcribe",
        }

    async def transcribe_and_summarize(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
    ) -> dict:
        """
        Transcribe audio and generate a structured summary alongside the full transcript.

        Returns:
            { "transcript": str, "summary": str, "key_points": [...], "operation": "transcribe_summarize" }
        """
        asset = await self._get_ready_audio(db, file_id, user_id)
        prompt = (
            "Please process this audio recording and provide:\n"
            "1. FULL TRANSCRIPT: The complete verbatim transcription.\n"
            "2. SUMMARY: A concise 2-3 sentence summary of the main content.\n"
            "3. KEY POINTS: Up to 5 bullet points of the most important information discussed.\n\n"
            "Format your response with clear section headers: 'FULL TRANSCRIPT:', 'SUMMARY:', 'KEY POINTS:'"
        )
        raw = await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)

        # Parse sections from structured response
        sections = {"transcript": raw, "summary": "", "key_points": []}
        try:
            if "SUMMARY:" in raw:
                parts = raw.split("SUMMARY:")
                if "FULL TRANSCRIPT:" in parts[0]:
                    sections["transcript"] = parts[0].split("FULL TRANSCRIPT:")[1].strip()
                summary_and_rest = parts[1]
                if "KEY POINTS:" in summary_and_rest:
                    summary_part, key_part = summary_and_rest.split("KEY POINTS:")
                    sections["summary"] = summary_part.strip()
                    sections["key_points"] = [
                        line.strip().lstrip("•-*0123456789. ")
                        for line in key_part.strip().split("\n")
                        if line.strip()
                    ]
                else:
                    sections["summary"] = summary_and_rest.strip()
        except Exception:
            pass  # Return raw if parsing fails

        return {
            "transcript": sections["transcript"],
            "summary": sections["summary"],
            "key_points": sections["key_points"],
            "operation": "transcribe_summarize",
        }

    async def translate_audio(
        self,
        db: AsyncSession,
        file_id: uuid.UUID,
        user_id: int,
        target_language: str,
    ) -> dict:
        """
        Transcribe audio and translate the content into the target language.

        Args:
            target_language: Target language name e.g. 'French', 'Hindi', 'Spanish'.

        Returns:
            { "original_transcript": str, "translation": str, "target_language": str, "operation": "translate" }
        """
        asset = await self._get_ready_audio(db, file_id, user_id)
        prompt = (
            f"Please process this audio recording:\n"
            f"1. ORIGINAL TRANSCRIPT: Transcribe the audio verbatim in its original language.\n"
            f"2. TRANSLATION: Translate the full transcript into {target_language}.\n\n"
            f"Format with headers: 'ORIGINAL TRANSCRIPT:' and 'TRANSLATION:'"
        )
        raw = await self._call_provider(asset.gemini_file_name, asset.mime_type, prompt)

        original = raw
        translation = ""
        try:
            if "TRANSLATION:" in raw:
                parts = raw.split("TRANSLATION:")
                if "ORIGINAL TRANSCRIPT:" in parts[0]:
                    original = parts[0].split("ORIGINAL TRANSCRIPT:")[1].strip()
                translation = parts[1].strip()
        except Exception:
            pass

        return {
            "original_transcript": original,
            "translation": translation,
            "target_language": target_language,
            "operation": "translate",
        }
