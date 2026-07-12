import asyncio
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseExecutionQueue(ABC):
    """Abstract execution job queue interface supporting Celery/Redis compatibility."""

    @abstractmethod
    async def enqueue(self, item: Any) -> None:
        """Enqueue step job."""
        pass

    @abstractmethod
    async def dequeue(self) -> Any:
        """Dequeue step job."""
        pass

    @abstractmethod
    def size(self) -> int:
        """Exposes current size of the queue."""
        pass


class AsyncExecutionQueue(BaseExecutionQueue):
    """Local AsyncIO event-loop execution queue implementation."""

    def __init__(self, maxsize: int = 100):
        self._queue = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, item: Any) -> None:
        await self._queue.put(item)

    async def dequeue(self) -> Any:
        return await self._queue.get()

    def size(self) -> int:
        return self._queue.qsize()

    def task_done(self) -> None:
        self._queue.task_done()
