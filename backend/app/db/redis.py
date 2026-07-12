import redis.asyncio as redis
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Initialize async Redis client lazily
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

async def check_redis_connection() -> bool:
    """Helper to verify Redis connectivity."""
    try:
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {str(e)}")
        return False
