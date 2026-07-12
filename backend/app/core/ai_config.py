from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class AIConfig(BaseSettings):
    # LLM Settings
    AI_PROVIDER: str = "gemini"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_MODEL: str = "gpt-4o"
    
    # LLM Hyperparameters
    GEMINI_TEMPERATURE: float = 0.7
    GEMINI_MAX_TOKENS: int = 8192
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2048
    CONTEXT_WINDOW_LIMIT: int = 16384

    # Embedding Settings
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    VECTOR_DB_PROVIDER: str = "pgvector"  # options: pgvector, chroma, qdrant

    # Default System Prompts
    DEFAULT_SYSTEM_PROMPT: str = (
        "You are VisionAI OS Assistant, a helpful and precise coding and productivity helper. "
        "Maintain a helpful, direct, and professional tone."
    )

    CODE_EXPLAINER_PROMPT: str = (
        "Analyze the following code. Explain how it works, its time/space complexity, "
        "and suggest any potential performance, design pattern, or security improvements."
    )

    BOWER_AUTOMATION_PROMPT: str = (
        "Generate a browser automation script based on the user's intent. "
        "Output executable Playwright Python code."
    )

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


ai_config = AIConfig()
