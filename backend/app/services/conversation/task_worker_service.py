from abc import ABC, abstractmethod
from typing import Any, Callable
from fastapi import BackgroundTasks
import logging

logger = logging.getLogger(__name__)


class TaskQueueInterface(ABC):
    """Abstract interface class representing background task/job execution workers."""

    @abstractmethod
    def enqueue(self, func: Callable, *args: Any, **kwargs: Any) -> None:
        """Add job payload arguments to the executor queue."""
        pass


class FastAPIBackgroundTaskQueue(TaskQueueInterface):
    """FastAPI context background task worker implementation, compliant with TaskQueueInterface."""

    def __init__(self, background_tasks: BackgroundTasks):
        self.background_tasks = background_tasks

    def enqueue(self, func: Callable, *args: Any, **kwargs: Any) -> None:
        logger.info(f"Enqueuing background task: {func.__name__} in FastAPI worker thread context.")
        self.background_tasks.add_task(func, *args, **kwargs)
