"""
Module 3 — TTSService: Text-to-Speech synthesis via Gemini TTS model.

Uses the Gemini 2.5 Flash Preview TTS model with AUDIO response modality.
Returns WAV audio bytes (raw PCM from Gemini wrapped in a standard WAV header).

Supported voices: Kore, Puck, Charon, Aoede, Fenrir, Leda, Orus, Zephyr
"""
import logging
import struct
from typing import List

from fastapi import HTTPException, status

from app.providers.provider_registry import provider_registry

logger = logging.getLogger(__name__)

# Available Gemini TTS voices with descriptions
AVAILABLE_VOICES: List[dict] = [
    {"name": "Kore",   "description": "Firm and confident — recommended for informational content"},
    {"name": "Puck",   "description": "Upbeat and energetic — great for casual conversations"},
    {"name": "Charon", "description": "Informative and clear — ideal for educational content"},
    {"name": "Aoede",  "description": "Breezy and easy-going — suitable for storytelling"},
    {"name": "Fenrir", "description": "Excitable and dynamic — best for enthusiastic narration"},
    {"name": "Leda",   "description": "Youthful and bright — good for friendly interfaces"},
    {"name": "Orus",   "description": "Confident and authoritative — effective for announcements"},
    {"name": "Zephyr", "description": "Bright and clear — optimal for general text reading"},
]

DEFAULT_VOICE = "Kore"
MAX_TEXT_LENGTH = 5000


class TTSService:
    """
    Text-to-Speech synthesis service using Gemini TTS models.
    Delegates synthesis to GeminiProvider.synthesize_speech() and returns WAV bytes.
    """

    def list_voices(self) -> List[dict]:
        """Return all available TTS voice names with descriptions."""
        return AVAILABLE_VOICES

    def validate_voice(self, voice: str) -> str:
        """Validate a voice name and return it normalized, falling back to default."""
        available_names = {v["name"].lower(): v["name"] for v in AVAILABLE_VOICES}
        normalized = available_names.get(voice.lower())
        if not normalized:
            logger.warning(
                f"Voice '{voice}' is not available. Falling back to '{DEFAULT_VOICE}'. "
                f"Available: {[v['name'] for v in AVAILABLE_VOICES]}"
            )
            return DEFAULT_VOICE
        return normalized

    async def synthesize(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
    ) -> bytes:
        """
        Convert text to speech using the Gemini TTS model.

        Args:
            text:  The text to synthesize (max 5000 characters).
            voice: Gemini TTS voice name (e.g. 'Kore', 'Puck').

        Returns:
            bytes: WAV audio data ready to stream to the client.

        Raises:
            HTTPException 400 if text is empty.
            HTTPException 422 if synthesis fails.
        """
        text = text.strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text for synthesis cannot be empty."
            )
        if len(text) > MAX_TEXT_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters. "
                       f"Provided: {len(text)} characters."
            )

        validated_voice = self.validate_voice(voice)

        try:
            provider = provider_registry.get("gemini")
            pcm_bytes = await provider.synthesize_speech(
                text=text,
                voice=validated_voice,
                settings_dict={},
            )
            # Wrap raw PCM in a WAV container for universal browser/player compatibility
            wav_bytes = self._pcm_to_wav(pcm_bytes)
            logger.info(
                f"TTS synthesis complete: voice={validated_voice}, "
                f"text_len={len(text)}, audio_bytes={len(wav_bytes)}"
            )
            return wav_bytes
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Text-to-Speech synthesis failed: {str(e)}"
            )

    @staticmethod
    def _pcm_to_wav(
        pcm_data: bytes,
        sample_rate: int = 24000,
        num_channels: int = 1,
        bits_per_sample: int = 16,
    ) -> bytes:
        """
        Prepend a standard WAV file header to raw PCM data from Gemini.

        Gemini TTS returns: signed 16-bit PCM, 24000 Hz, mono.
        This function wraps it in a RIFF/WAV container so any media player can decode it.
        """
        num_samples = len(pcm_data)
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        data_chunk_size = num_samples
        riff_chunk_size = 36 + data_chunk_size

        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",           # ChunkID
            riff_chunk_size,   # ChunkSize
            b"WAVE",           # Format
            b"fmt ",           # Subchunk1ID
            16,                # Subchunk1Size (PCM = 16)
            1,                 # AudioFormat (PCM = 1)
            num_channels,      # NumChannels
            sample_rate,       # SampleRate
            byte_rate,         # ByteRate
            block_align,       # BlockAlign
            bits_per_sample,   # BitsPerSample
            b"data",           # Subchunk2ID
            data_chunk_size,   # Subchunk2Size
        )
        return header + pcm_data
