import json
import uuid
from typing import Any, Dict
from app.db.redis import redis_client

class StatusService:
    """Service layer managing real-time generation status registers (thinking, streaming, cancelled) in Redis."""

    def __init__(self):
        self.client = redis_client

    def _get_key(self, conversation_id: uuid.UUID) -> str:
        return f"status:conversation:{conversation_id}"

    def _get_cancel_key(self, conversation_id: uuid.UUID) -> str:
        return f"cancel:conversation:{conversation_id}"

    async def set_status(
        self,
        conversation_id: uuid.UUID,
        status: str,
        provider: str = "gemini",
        elapsed_ms: int = 0,
        tokens_generated: int = 0
    ) -> None:
        """Set real-time status attributes in Redis with a 1-hour expiration."""
        key = self._get_key(conversation_id)
        data = {
            "status": status,
            "provider": provider,
            "elapsed_ms": str(elapsed_ms),
            "tokens_generated": str(tokens_generated)
        }
        await self.client.hset(key, mapping=data)
        await self.client.expire(key, 3600)  # TTL of 1 hour

    async def get_status(self, conversation_id: uuid.UUID) -> Dict[str, Any]:
        """Fetch status values from Redis, returning IDLE defaults if not found."""
        key = self._get_key(conversation_id)
        data = await self.client.hgetall(key)
        if not data:
            return {
                "status": "IDLE",
                "provider": "gemini",
                "elapsed_ms": 0,
                "tokens_generated": 0
            }
        return {
            "status": data.get("status", "IDLE"),
            "provider": data.get("provider", "gemini"),
            "elapsed_ms": int(data.get("elapsed_ms", 0)),
            "tokens_generated": int(data.get("tokens_generated", 0))
        }

    async def set_cancelled(self, conversation_id: uuid.UUID) -> None:
        """Signal cancellation for active stream loops."""
        cancel_key = self._get_cancel_key(conversation_id)
        await self.client.set(cancel_key, "true", ex=60)  # 60s TTL
        await self.set_status(conversation_id, "CANCELLED")

    async def is_cancelled(self, conversation_id: uuid.UUID) -> bool:
        """Check if cancellation has been requested."""
        cancel_key = self._get_cancel_key(conversation_id)
        val = await self.client.get(cancel_key)
        return val == "true"

    async def clear_cancel(self, conversation_id: uuid.UUID) -> None:
        """Clear cancellation signal."""
        await self.client.delete(self._get_cancel_key(conversation_id))

    async def clear_status(self, conversation_id: uuid.UUID) -> None:
        """Wipe status records from Redis."""
        await self.client.delete(self._get_key(conversation_id))
