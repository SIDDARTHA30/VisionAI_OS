import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import auth, conversations
from app.api.endpoints import files, vision, documents, speech, multimodal_chat, automation
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.db.database import engine, Base
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.core.exceptions import AIProviderException, ai_provider_exception_handler
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError
from app.services.automation.exceptions import (
    AutomationError,
    InvalidStateTransitionError,
    ConcurrencyConflictError,
    ApprovalRequiredError,
    ExecutionNotFoundError,
    TaskNotFoundError
)

# Setup overall logging config
setup_logging()
logger = logging.getLogger("main_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        # Create all declared tables if they do not exist
        # Importing models here ensures they are registered with Base.metadata
        import app.models.file_asset  # noqa: F401
        import app.models.automation  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialization complete.")

    # Ensure local upload directory exists (Module 3)
    upload_dir = getattr(settings, "UPLOAD_DIR", "/app/uploads")
    os.makedirs(upload_dir, exist_ok=True)
    logger.info(f"Upload directory ready: {upload_dir}")

    yield
    # Shutdown actions
    logger.info("Shutting down async engine...")
    await engine.dispose()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    lifespan=lifespan
)

# Register AI provider exception handler
app.add_exception_handler(AIProviderException, ai_provider_exception_handler)

# 1. Custom Automation Exception Handler
@app.exception_handler(AutomationError)
async def automation_exception_handler(request, exc: AutomationError):
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, ConcurrencyConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, ApprovalRequiredError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (TaskNotFoundError, ExecutionNotFoundError)):
        status_code = status.HTTP_404_NOT_FOUND
        
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": exc.message,
            "data": None
        }
    )

# 2. SQLAlchemy StaleDataError handler (optimistic locking conflicts)
@app.exception_handler(StaleDataError)
async def stale_data_exception_handler(request, exc: StaleDataError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "success": False,
            "message": "Concurrency conflict: This record has been modified by another process. Please reload.",
            "data": None
        }
    )

# 3. RequestValidationError handler (Pydantic validations)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    errors = exc.errors()
    message = "Request validation failed."
    if errors:
        # Extract a user-friendly summary of the first error
        first_err = errors[0]
        loc = " -> ".join(str(l) for l in first_err.get("loc", []))
        message = f"Validation failed at '{loc}': {first_err.get('msg')}"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": message,
            "data": None
        }
    )

# 4. Global HTTPException handler (FastAPI HTTPExceptions)
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "data": None
        }
    )

# CORS configuration
if settings.CORS_ORIGINS:
    origins = [str(origin).strip("/") for origin in settings.CORS_ORIGINS]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Security and Logger middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# API Route registrations — Phase 1 & 2
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(conversations.router, prefix=f"{settings.API_V1_STR}/conversations", tags=["conversations"])
app.include_router(conversations.msg_router, prefix=f"{settings.API_V1_STR}/messages", tags=["messages"])

# API Route registrations — Phase 3: Multimodal Intelligence Layer
app.include_router(files.router, prefix=f"{settings.API_V1_STR}/files", tags=["files"])
app.include_router(vision.router, prefix=f"{settings.API_V1_STR}/vision", tags=["vision"])
app.include_router(documents.router, prefix=f"{settings.API_V1_STR}/documents", tags=["documents"])
app.include_router(speech.router, prefix=f"{settings.API_V1_STR}/speech", tags=["speech"])
app.include_router(multimodal_chat.router, prefix=f"{settings.API_V1_STR}/conversations", tags=["multimodal-chat"])
app.include_router(automation.router, prefix=f"{settings.API_V1_STR}/automation", tags=["automation"])


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint to ensure server is running."""
    return {"status": "ok", "project": settings.PROJECT_NAME}


@app.get(f"{settings.API_V1_STR}/health/ai", tags=["health"])
async def ai_health_check():
    """Verify AI provider configuration and connectivity with metrics."""
    from app.providers.provider_registry import provider_registry
    from app.core.ai_config import ai_config
    import time
    
    provider_name = "gemini"
    start_time = time.time()
    reason = None
    status_val = "healthy"
    latency_ms = 0
    
    try:
        provider = provider_registry.get(provider_name)
        await provider.count_tokens("health check")
        latency_ms = int((time.time() - start_time) * 1000)
    except Exception as e:
        status_val = "unhealthy"
        latency_ms = int((time.time() - start_time) * 1000)
        err_msg = str(e).lower()
        if "429" in err_msg or "resource_exhausted" in err_msg:
            reason = "quota_exceeded"
        elif "api_key" in err_msg or "api key" in err_msg or "invalid" in err_msg:
            reason = "invalid_api_key"
        else:
            reason = f"api_error: {str(e)}"
            
    response_payload = {
        "provider": provider_name,
        "model": ai_config.GEMINI_MODEL,
        "status": status_val,
    }
    if status_val == "healthy":
        response_payload["latency_ms"] = latency_ms
    else:
        response_payload["reason"] = reason
        
    return response_payload
