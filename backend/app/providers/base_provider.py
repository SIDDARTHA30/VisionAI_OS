from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Union


class BaseProvider(ABC):
    """Abstract Base Class specifying capabilities and APIs for LLM provider adapters."""

    @abstractmethod
    async def generate_response(
        self, 
        messages: List[Dict[str, str]], 
        settings: Dict[str, Any], 
        **kwargs
    ) -> str:
        """Submit messages list to the provider and return the full text response."""
        pass

    @abstractmethod
    async def generate_stream(
        self, 
        messages: List[Dict[str, str]], 
        settings: Dict[str, Any], 
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Submit messages list and yield text chunks in real-time."""
        pass

    @abstractmethod
    async def count_tokens(
        self, 
        text_or_messages: Union[str, List[Dict[str, str]]]
    ) -> int:
        """Calculate and return the number of tokens for the inputs."""
        pass

    @abstractmethod
    def supports_vision(self) -> bool:
        """Check if the provider supports image/vision ingestion."""
        pass

    @abstractmethod
    def supports_streaming(self) -> bool:
        """Check if the provider supports chunk-based streaming responses."""
        pass

    @abstractmethod
    def supports_function_calling(self) -> bool:
        """Check if the provider supports tools and function calling."""
        pass

    @abstractmethod
    def supports_json_mode(self) -> bool:
        """Check if the provider supports structured JSON output configurations."""
        pass

    # ─── Module 3: Multimodal Extensions ─────────────────────────────────────

    @abstractmethod
    async def analyze_file(
        self,
        gemini_file_name: str,
        mime_type: str,
        prompt: str,
        settings_dict: Dict[str, Any],
    ) -> str:
        """
        Analyze a file (image, audio, document) already uploaded to the Gemini Files API.
        The gemini_file_name is the name returned by client.files.upload() (e.g. 'files/abc123').
        Returns the model's text response to the prompt.
        """
        pass

    @abstractmethod
    async def synthesize_speech(
        self,
        text: str,
        voice: str,
        settings_dict: Dict[str, Any],
    ) -> bytes:
        """
        Convert text to speech using the provider's TTS model.
        Returns raw PCM audio bytes (signed 16-bit, 24000 Hz, mono).
        The caller is responsible for wrapping in a WAV container if needed.
        """
        pass

    @abstractmethod
    async def generate_multimodal_response(
        self,
        messages: List[Dict[str, str]],
        file_assets: List[Dict[str, str]],
        user_text: str,
        settings_dict: Dict[str, Any],
    ) -> str:
        """
        Generate a response to a message that combines conversation history text
        with one or more file attachments (images, documents).

        Args:
            messages:    Existing conversation history in standard format [{role, content}].
            file_assets: List of dicts with 'gemini_file_name' and 'mime_type' keys.
            user_text:   The current user's text message.
            settings_dict: Model configuration (model, temperature, max_tokens, system_prompt).

        Returns:
            The assistant's text response.
        """
        pass
