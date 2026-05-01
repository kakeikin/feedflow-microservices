import os
import json
import logging
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
FEED_TTL = 300  # 5 minutes

_redis: aioredis.Redis | None = None


async def connect() -> None:
    global _redis
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)


async def disconnect() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def get_feed(user_id: str) -> list[dict] | None:
    if _redis is None:
        return None
    try:
        data = await _redis.get(f"feed:user:{user_id}")
        return json.loads(data) if data else None
    except Exception:
        logger.warning("Redis get failed for feed:user:%s", user_id)
        return None


async def set_feed(user_id: str, items: list[dict]) -> None:
    if _redis is None:
        return
    try:
        await _redis.setex(f"feed:user:{user_id}", FEED_TTL, json.dumps(items))
    except Exception:
        logger.warning("Redis set failed for feed:user:%s", user_id)
