import asyncio
import json
from unittest.mock import AsyncMock


def test_get_feed_returns_cached_data():
    from app import cache
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps([{"video_id": "v1", "score": 0.9, "reason": "ai"}])
    cache._redis = mock_redis

    result = asyncio.run(cache.get_feed("u1"))

    assert result == [{"video_id": "v1", "score": 0.9, "reason": "ai"}]
    mock_redis.get.assert_awaited_once_with("feed:user:u1")
    cache._redis = None


def test_get_feed_returns_none_on_cache_miss():
    from app import cache
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    cache._redis = mock_redis

    result = asyncio.run(cache.get_feed("u1"))

    assert result is None
    cache._redis = None


def test_get_feed_returns_none_when_redis_unavailable():
    from app import cache
    cache._redis = None

    result = asyncio.run(cache.get_feed("u1"))

    assert result is None


def test_set_feed_stores_with_ttl():
    from app import cache
    mock_redis = AsyncMock()
    cache._redis = mock_redis

    items = [{"video_id": "v1", "score": 0.9, "reason": "ai"}]
    asyncio.run(cache.set_feed("u1", items))

    mock_redis.setex.assert_awaited_once_with("feed:user:u1", 300, json.dumps(items))
    cache._redis = None


def test_set_feed_no_op_when_redis_unavailable():
    from app import cache
    cache._redis = None

    asyncio.run(cache.set_feed("u1", []))  # must not raise


def test_get_feed_swallows_redis_exception():
    from app import cache
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("connection lost")
    cache._redis = mock_redis

    result = asyncio.run(cache.get_feed("u1"))

    assert result is None
    cache._redis = None


def test_set_feed_swallows_redis_exception():
    from app import cache
    mock_redis = AsyncMock()
    mock_redis.setex.side_effect = Exception("write timeout")
    cache._redis = mock_redis

    asyncio.run(cache.set_feed("u1", [{"video_id": "v1"}]))  # must not raise

    cache._redis = None
