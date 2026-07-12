import logging
import traceback
from typing import Any, Dict, Optional
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.core.exceptions")


class AIProviderException(Exception):
    """Base exception for all AI Provider related errors."""
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        provider: str = "Gemini",
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.provider = provider
        self.retry_after = retry_after
        self.details = details or {}
        self.context = context or {}
        super().__init__(message)


class AIProviderQuotaExceededException(AIProviderException):
    def __init__(self, message: str, retry_after: Optional[int] = None, details: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=429,
            error_code="RESOURCE_EXHAUSTED",
            message=message,
            retry_after=retry_after,
            details=details,
            context=context
        )


class AIProviderAuthException(AIProviderException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=401,
            error_code="AUTHENTICATION_FAILED",
            message=message,
            details=details,
            context=context
        )


class AIProviderInvalidRequestException(AIProviderException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=400,
            error_code="INVALID_REQUEST",
            message=message,
            details=details,
            context=context
        )


class AIProviderUnavailableException(AIProviderException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=503,
            error_code="PROVIDER_UNAVAILABLE",
            message=message,
            details=details,
            context=context
        )


class AIProviderTimeoutException(AIProviderException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=504,
            error_code="REQUEST_TIMEOUT",
            message=message,
            details=details,
            context=context
        )


class AIProviderUnsupportedFileException(AIProviderException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=415,
            error_code="UNSUPPORTED_FILE",
            message=message,
            details=details,
            context=context
        )


def map_gemini_exception(e: Exception, context_info: Optional[Dict[str, Any]] = None) -> AIProviderException:
    """
    Inspects a Gemini / GenAI SDK exception and returns a structured AIProviderException.
    Also extracts retry_after values if specified in the API response.
    """
    err_msg = str(e)
    ctx = context_info or {}

    # Extract retry delay (e.g. "Please retry in 36s" or from custom delay rules)
    retry_after = None
    try:
        err_msg_lower = err_msg.lower()
        if "retry in" in err_msg_lower:
            parts = err_msg_lower.split("retry in")
            if len(parts) > 1:
                num_str = "".join([c for c in parts[1].split()[0] if c.isdigit()])
                if num_str:
                    retry_after = int(num_str)
    except Exception:
        pass

    # Map to appropriate subclass
    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
        exc = AIProviderQuotaExceededException(
            message="Gemini quota exceeded",
            retry_after=retry_after,
            details={"original_message": err_msg},
            context=ctx
        )
    elif "401" in err_msg or "api key not valid" in err_msg_lower or "api_key_invalid" in err_msg_lower:
        exc = AIProviderAuthException(
            message="Gemini authentication failed. Please pass a valid API key.",
            details={"original_message": err_msg},
            context=ctx
        )
    elif "400" in err_msg or "INVALID_ARGUMENT" in err_msg:
        exc = AIProviderInvalidRequestException(
            message="Invalid request sent to Gemini.",
            details={"original_message": err_msg},
            context=ctx
        )
    elif "503" in err_msg or "UNAVAILABLE" in err_msg:
        exc = AIProviderUnavailableException(
            message="Gemini provider is currently unavailable.",
            details={"original_message": err_msg},
            context=ctx
        )
    elif "504" in err_msg or "DEADLINE_EXCEEDED" in err_msg:
        exc = AIProviderTimeoutException(
            message="Request to Gemini timed out.",
            details={"original_message": err_msg},
            context=ctx
        )
    elif "unsupported file" in err_msg_lower or "415" in err_msg:
        exc = AIProviderUnsupportedFileException(
            message="Unsupported file type sent to Gemini.",
            details={"original_message": err_msg},
            context=ctx
        )
    else:
        # Fallback to general exception
        exc = AIProviderException(
            status_code=500,
            error_code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred during Gemini processing.",
            details={"original_message": err_msg},
            context=ctx
        )

    # Detailed structured logging as requested
    logger.error(
        f"AI Provider failure logged:\n"
        f"  - Provider: {exc.provider}\n"
        f"  - Operation: {ctx.get('operation', 'N/A')}\n"
        f"  - Model: {ctx.get('model', 'N/A')}\n"
        f"  - File ID: {ctx.get('file_id', 'N/A')}\n"
        f"  - User ID: {ctx.get('user_id', 'N/A')}\n"
        f"  - Conversation ID: {ctx.get('conversation_id', 'N/A')}\n"
        f"  - HTTP status: {exc.status_code}\n"
        f"  - Retry delay: {exc.retry_after if exc.retry_after is not None else 'N/A'}\n"
        f"  - Original response: {err_msg}\n"
        f"  - Stack trace:\n{traceback.format_exc()}"
    )

    return exc


async def ai_provider_exception_handler(request: Request, exc: AIProviderException) -> JSONResponse:
    """FastAPI handler to return clean JSON payload when AIProviderException is raised."""
    content = {
        "error": exc.message,
        "provider": exc.provider,
        "code": exc.error_code,
        "message": exc.details.get("original_message", exc.message)
    }
    if exc.retry_after is not None:
        content["retry_after"] = exc.retry_after

    return JSONResponse(
        status_code=exc.status_code,
        content=content
    )
