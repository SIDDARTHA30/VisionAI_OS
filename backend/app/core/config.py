import os
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "VisionAI-OS"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database Settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/visionai_db"

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security & Auth Settings
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS Origins (Comma-separated list converted to list of strings)
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Third Party AI APIs
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""

    # Module 3 — Multimodal File Storage
    UPLOAD_DIR: str = "/app/uploads"
    MAX_IMAGE_SIZE_MB: int = 50
    MAX_AUDIO_SIZE_MB: int = 50
    MAX_DOCUMENT_SIZE_MB: int = 200

    # Module 3 — TTS Defaults
    TTS_DEFAULT_VOICE: str = "Kore"
    TTS_MODEL: str = "gemini-2.5-flash-preview-tts"

    # Module 4 — Automation Execution Engine Policy
    AUTOMATION_MAX_PARALLEL_STEPS: int = 4
    AUTOMATION_DEFAULT_TIMEOUT_SEC: int = 60
    AUTOMATION_MAX_RETRIES: int = 3
    AUTOMATION_BACKOFF_FACTOR: float = 2.0
    AUTOMATION_QUEUE_SIZE: int = 100


    # Configuration source
    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"
        ),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
