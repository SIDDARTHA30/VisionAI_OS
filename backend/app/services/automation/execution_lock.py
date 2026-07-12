import asyncio
import uuid
from typing import Set


class ExecutionLockManager:
    """Manages transaction locks preventing concurrent runs on a single task."""

    def __init__(self):
        self._active_locks: Set[uuid.UUID] = set()
        self._lock = asyncio.Lock()

    async def acquire_lock(self, task_id: uuid.UUID) -> bool:
        """Acquires execution lock. Returns True if successful, else False."""
        async with self._lock:
            if task_id in self._active_locks:
                return False
            self._active_locks.add(task_id)
            return True

    async def release_lock(self, task_id: uuid.UUID) -> None:
        """Releases lock for a task."""
        async with self._lock:
            if task_id in self._active_locks:
                self._active_locks.remove(task_id)


# Global lock instance
execution_locks = ExecutionLockManager()
