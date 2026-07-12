import asyncio
import logging
from typing import Callable, Any, Awaitable
from app.services.automation.execution_error import RetryableError, PermanentError

logger = logging.getLogger(__name__)


class RetryEngine:
    """Manages execution retries with exponential backoff configurations."""

    async def execute_with_retry(
        self,
        operation: Callable[[], Awaitable[Any]],
        max_retries: int,
        initial_delay: float,
        backoff_factor: float,
        retry_callback: Callable[[Exception, int], Awaitable[None]] = None
    ) -> Any:
        """Executes operations, catching RetryableError and triggering backoffs."""
        delay = initial_delay
        for attempt in range(max_retries + 1):
            try:
                return await operation()
            except PermanentError as pe:
                logger.error(f"Permanent error encountered. Aborting retries immediately: {pe}")
                raise pe
            except Exception as e:
                # Catch any error, but classify: if not classified, treat as Retryable
                is_retryable = not isinstance(e, PermanentError)
                if not is_retryable or attempt >= max_retries:
                    logger.error(f"Retry attempts exhausted ({attempt}/{max_retries}) or error not retryable: {e}")
                    raise e

                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed with error: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                if retry_callback:
                    await retry_callback(e, attempt + 1)

                await asyncio.sleep(delay)
                delay *= backoff_factor
