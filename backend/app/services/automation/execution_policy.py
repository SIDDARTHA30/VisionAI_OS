from pydantic import BaseModel
from app.core.config import settings


class ExecutionPolicy(BaseModel):
    """Execution bounds, retries, concurrency limits and timings configuration."""
    max_parallel_steps: int = settings.AUTOMATION_MAX_PARALLEL_STEPS
    default_timeout_sec: int = settings.AUTOMATION_DEFAULT_TIMEOUT_SEC
    max_retries: int = settings.AUTOMATION_MAX_RETRIES
    backoff_factor: float = settings.AUTOMATION_BACKOFF_FACTOR
    queue_size: int = settings.AUTOMATION_QUEUE_SIZE
    workspace_limit_mb: int = 500  # Default sandbox limit
    sandbox_limit_files: int = 1000

# Global shared execution policy
execution_policy = ExecutionPolicy()
