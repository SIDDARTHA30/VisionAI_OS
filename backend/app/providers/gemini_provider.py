from typing import Any, AsyncGenerator, Dict, List, Union
import asyncio
from google import genai
from google.genai import types
from google.genai.errors import APIError
import logging

logger = logging.getLogger(__name__)


def _parse_retry_delay(err_msg: str, default: float) -> float:
    if "retry in" in err_msg:
        try:
            parts = err_msg.split("retry in")
            token = parts[1].strip().split()[0]
            clean_token = "".join(c for c in token if c.isdigit() or c == ".")
            if clean_token:
                return float(clean_token)
        except Exception:
            pass
    return default

from app.core.config import settings
from app.core.ai_config import ai_config
from app.providers.base_provider import BaseProvider
from app.core.exceptions import map_gemini_exception


class GeminiProvider(BaseProvider):
    """Google GenAI SDK implementation adapter for Gemini models."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = genai.Client(api_key=settings.GOOGLE_API_KEY or "MOCK_KEY_FOR_TESTS")
        return self._client

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[types.Content]:
        """Convert standard format [{role, content}] into Gemini Content structures."""
        converted = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            # Map roles: FastAPI assistant -> model
            gemini_role = "model" if role == "assistant" else role
            
            # Skip system prompts from direct chat history (handled in settings config)
            if role == "system":
                continue
                
            converted.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part.from_text(text=content)]
                )
            )
        return converted

    def _build_config(self, settings_dict: Dict[str, Any]) -> types.GenerateContentConfig:
        """Construct GenerateContentConfig based on conversation settings."""
        config_args = {}
        
        if "temperature" in settings_dict:
            config_args["temperature"] = float(settings_dict["temperature"])
            
        if "max_tokens" in settings_dict:
            config_args["max_output_tokens"] = int(settings_dict["max_tokens"])
            
        if "system_prompt" in settings_dict and settings_dict["system_prompt"]:
            config_args["system_instruction"] = str(settings_dict["system_prompt"])
            
        return types.GenerateContentConfig(**config_args)

    async def generate_response(
        self, 
        messages: List[Dict[str, str]], 
        settings_dict: Dict[str, Any], 
        **kwargs
    ) -> str:
        """Call models.generate_content synchronously using the client executor."""
        model = settings_dict.get("model", ai_config.GEMINI_MODEL)
        contents = self._convert_messages(messages)
        config = self._build_config(settings_dict)

        max_retries = 3
        delay = 1.0
        for attempt in range(max_retries):
            try:
                logger.info("Using Gemini model: %s", model)
                # The client SDK calls are synchronous underneath.
                # Running them directly or wrapping in executor prevents thread blocking.
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                return response.text or ""
            except Exception as e:
                err_msg = str(e)
                is_transient = "429" in err_msg or "500" in err_msg or "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
                if is_transient and attempt < max_retries - 1:
                    wait_time = _parse_retry_delay(err_msg, delay)
                    logger.warning(
                        f"Gemini API transient failure (attempt {attempt + 1}/{max_retries}): {err_msg}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    # If we parsed a custom delay, don't double the default backoff
                    if wait_time == delay:
                        delay *= 2.0
                else:
                    raise map_gemini_exception(
                        e,
                        context_info={"operation": "generate_response", "model": model}
                    )

    async def generate_stream(
        self, 
        messages: List[Dict[str, str]], 
        settings_dict: Dict[str, Any], 
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Yield response chunks using generate_content_stream."""
        model = settings_dict.get("model", ai_config.GEMINI_MODEL)
        contents = self._convert_messages(messages)
        config = self._build_config(settings_dict)

        max_retries = 3
        delay = 1.0
        for attempt in range(max_retries):
            try:
                logger.info("Using Gemini model: %s", model)
                response_stream = self.client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=config
                )
                for chunk in response_stream:
                    if chunk.text:
                        yield chunk.text
                break
            except Exception as e:
                err_msg = str(e)
                is_transient = "429" in err_msg or "500" in err_msg or "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
                if is_transient and attempt < max_retries - 1:
                    wait_time = _parse_retry_delay(err_msg, delay)
                    logger.warning(
                        f"Gemini API streaming transient failure (attempt {attempt + 1}/{max_retries}): {err_msg}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    if wait_time == delay:
                        delay *= 2.0
                else:
                    raise map_gemini_exception(
                        e,
                        context_info={"operation": "generate_stream", "model": model}
                    )

    async def count_tokens(
        self, 
        text_or_messages: Union[str, List[Dict[str, str]]]
    ) -> int:
        """Count tokens of text or mapped message payloads."""
        # For simplicity, count tokens using the default models
        model = ai_config.GEMINI_MODEL
        if isinstance(text_or_messages, str):
            contents = text_or_messages
        else:
            contents = self._convert_messages(text_or_messages)

        try:
            result = self.client.models.count_tokens(
                model=model,
                contents=contents
            )
            return result.total_tokens
        except Exception:
            # Fallback estimation: ~4 characters per token
            if isinstance(text_or_messages, str):
                return len(text_or_messages) // 4
            return sum(len(m.get("content", "")) for m in text_or_messages) // 4

    def supports_vision(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True

    def supports_function_calling(self) -> bool:
        return True

    def supports_json_mode(self) -> bool:
        return True

    # ─── Module 3: Multimodal Extensions ──────────────────────────────────────

    async def analyze_file(
        self,
        gemini_file_name: str,
        mime_type: str,
        prompt: str,
        settings_dict: Dict[str, Any],
    ) -> str:
        """
        Analyze a file already uploaded to the Gemini Files API using its file name.
        Re-fetches the file object from Gemini, then calls generate_content with the prompt.
        Inherits the same retry logic pattern as generate_response.
        """
        model = settings_dict.get("model", ai_config.GEMINI_MODEL)

        max_retries = 3
        delay = 1.0
        for attempt in range(max_retries):
            try:
                logger.info("Analyzing file via Gemini: name=%s, mime=%s", gemini_file_name, mime_type)
                # Re-fetch the file object so the SDK can embed it as a Part
                loop = asyncio.get_event_loop()
                gemini_file = await loop.run_in_executor(
                    None,
                    lambda: self.client.files.get(name=gemini_file_name)
                )
                response = self.client.models.generate_content(
                    model=model,
                    contents=[prompt, gemini_file],
                )
                return response.text or ""
            except Exception as e:
                err_msg = str(e)
                is_transient = "429" in err_msg or "500" in err_msg or "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
                if is_transient and attempt < max_retries - 1:
                    wait_time = _parse_retry_delay(err_msg, delay)
                    logger.warning(
                        f"Gemini analyze_file transient failure (attempt {attempt + 1}/{max_retries}): {err_msg}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    if wait_time == delay:
                        delay *= 2.0
                else:
                    raise map_gemini_exception(
                        e,
                        context_info={"operation": "analyze_file", "model": model}
                    )

    async def synthesize_speech(
        self,
        text: str,
        voice: str,
        settings_dict: Dict[str, Any],
    ) -> bytes:
        """
        Use the Gemini TTS model to synthesize speech from text.
        Returns raw PCM bytes (signed 16-bit, 24000 Hz, mono).
        The TTSService caller wraps this in a WAV header.
        """
        tts_model = "gemini-2.5-flash-preview-tts"
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        )

        max_retries = 3
        delay = 1.0
        for attempt in range(max_retries):
            try:
                logger.info("Gemini TTS synthesis: model=%s, voice=%s, text_len=%d", tts_model, voice, len(text))
                response = self.client.models.generate_content(
                    model=tts_model,
                    contents=text,
                    config=config,
                )
                # Extract PCM bytes from inline_data
                pcm_bytes = response.candidates[0].content.parts[0].inline_data.data
                return pcm_bytes
            except Exception as e:
                err_msg = str(e)
                is_transient = "429" in err_msg or "500" in err_msg or "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
                if is_transient and attempt < max_retries - 1:
                    wait_time = _parse_retry_delay(err_msg, delay)
                    logger.warning(
                        f"Gemini TTS transient failure (attempt {attempt + 1}/{max_retries}): {err_msg}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    if wait_time == delay:
                        delay *= 2.0
                else:
                    raise map_gemini_exception(
                        e,
                        context_info={"operation": "synthesize_speech", "model": tts_model}
                    )

    async def generate_multimodal_response(
        self,
        messages: List[Dict[str, str]],
        file_assets: List[Dict[str, str]],
        user_text: str,
        settings_dict: Dict[str, Any],
    ) -> str:
        """
        Generate a response combining conversation history with file attachments.

        Builds a Gemini contents list:
            [history_turns..., user_text_part, file_part_1, file_part_2, ...]

        The model sees the full context and all attached files simultaneously.
        """
        model = settings_dict.get("model", ai_config.GEMINI_MODEL)
        config = self._build_config(settings_dict)

        # Convert existing conversation history (exclude system messages handled in config)
        history_contents = self._convert_messages(messages)

        # Fetch Gemini file objects for each attachment
        loop = asyncio.get_event_loop()
        file_parts = []
        for asset_info in file_assets:
            gemini_file_name = asset_info.get("gemini_file_name")
            if gemini_file_name:
                try:
                    gemini_file = await loop.run_in_executor(
                        None,
                        lambda name=gemini_file_name: self.client.files.get(name=name)
                    )
                    file_parts.append(gemini_file)
                except Exception as e:
                    logger.warning(f"Failed to fetch Gemini file '{gemini_file_name}': {e}")

        # Build the final user turn: text + all file references
        user_parts = [types.Part.from_text(text=user_text)] + [
            types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type) if hasattr(f, 'uri') else f
            for f in file_parts
        ]
        user_content = types.Content(role="user", parts=user_parts)

        # Full contents: history + current multimodal user turn
        contents = history_contents + [user_content]

        max_retries = 3
        delay = 1.0
        for attempt in range(max_retries):
            try:
                logger.info(
                    "Gemini multimodal generation: model=%s, history=%d turns, files=%d",
                    model, len(history_contents), len(file_parts)
                )
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                return response.text or ""
            except Exception as e:
                err_msg = str(e)
                is_transient = "429" in err_msg or "500" in err_msg or "503" in err_msg or "RESOURCE_EXHAUSTED" in err_msg
                if is_transient and attempt < max_retries - 1:
                    wait_time = _parse_retry_delay(err_msg, delay)
                    logger.warning(
                        f"Gemini multimodal transient failure (attempt {attempt + 1}/{max_retries}): {err_msg}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    if wait_time == delay:
                        delay *= 2.0
                else:
                    raise map_gemini_exception(
                        e,
                        context_info={"operation": "generate_multimodal_response", "model": model}
                    )
