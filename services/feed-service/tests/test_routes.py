import pytest
import httpx
from starlette.testclient import TestClient
from app.main import app

TRENDING = [
    {
        "id": "v1",
        "title": "AI Video",
        "creator_id": "u1",
        "tags": ["ai"],
        "duration_seconds": 60,
        "created_at": "2026-01-01T00:00:00",
        "stats": {"views": 10, "likes": 5, "skips": 0, "completion_rate": 0.8},
    }
]
RANKED = [{"video_id": "v1", "score": 0.91, "reason": "matched user interest tags: ai"}]


def test_feed_returns_personalized_when_ranking_succeeds(monkeypatch):
    async def mock_get_trending():
        return TRENDING

    async def mock_rank(user_id, video_ids):
        return RANKED

    monkeypatch.setattr("app.routes.clients.get_trending_videos", mock_get_trending)
    monkeypatch.setattr("app.routes.clients.rank_videos", mock_rank)

    with TestClient(app) as client:
        response = client.get("/feed/user-123")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "personalized_ranking"
    assert data["user_id"] == "user-123"
    assert data["items"][0]["video_id"] == "v1"
    assert data["items"][0]["score"] == 0.91


def test_feed_falls_back_when_ranking_fails(monkeypatch):
    async def mock_get_trending():
        return TRENDING

    async def mock_rank_fails(user_id, video_ids):
        raise httpx.ConnectError("ranking service down")

    monkeypatch.setattr("app.routes.clients.get_trending_videos", mock_get_trending)
    monkeypatch.setattr("app.routes.clients.rank_videos", mock_rank_fails)

    with TestClient(app) as client:
        response = client.get("/feed/user-123")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "trending_fallback"
    assert data["items"][0]["score"] == 0.0
    assert data["items"][0]["reason"] == "trending_fallback"
    assert data["items"][0]["video_id"] == "v1"


CACHED_ITEMS = [{"video_id": "v1", "score": 0.91, "reason": "ai"}]


def test_feed_returns_cache_hit_when_cached(monkeypatch):
    """When cache.get_feed returns data, source is cache_hit and upstream is not called."""
    async def mock_get_feed(user_id):
        return CACHED_ITEMS

    async def must_not_be_called(*args, **kwargs):
        raise AssertionError("upstream client called on cache hit")

    monkeypatch.setattr("app.routes.cache.get_feed", mock_get_feed)
    monkeypatch.setattr("app.routes.clients.get_trending_videos", must_not_be_called)
    monkeypatch.setattr("app.routes.clients.rank_videos", must_not_be_called)

    with TestClient(app) as client:
        resp = client.get("/feed/user-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "cache_hit"
    assert data["items"][0]["video_id"] == "v1"
    assert data["items"][0]["score"] == 0.91


def test_feed_calls_ranking_when_cache_returns_none(monkeypatch):
    """Cache miss (get_feed returns None) triggers the trending → ranking flow."""
    async def mock_get_feed(user_id):
        return None

    async def mock_set_feed(user_id, items):
        pass

    async def mock_get_trending():
        return TRENDING

    async def mock_rank(user_id, video_ids):
        return RANKED

    monkeypatch.setattr("app.routes.cache.get_feed", mock_get_feed)
    monkeypatch.setattr("app.routes.cache.set_feed", mock_set_feed)
    monkeypatch.setattr("app.routes.clients.get_trending_videos", mock_get_trending)
    monkeypatch.setattr("app.routes.clients.rank_videos", mock_rank)

    with TestClient(app) as client:
        resp = client.get("/feed/user-123")

    assert resp.status_code == 200
    assert resp.json()["source"] == "personalized_ranking"


def test_feed_attempts_set_feed_even_when_cache_read_failed(monkeypatch):
    """Even when get_feed returns None (Redis unavailable on read), set_feed is still called."""
    set_feed_called = []

    async def mock_get_feed(user_id):
        return None  # simulates Redis unavailable on read

    async def mock_set_feed(user_id, items):
        set_feed_called.append(True)

    async def mock_get_trending():
        return TRENDING

    async def mock_rank(user_id, video_ids):
        return RANKED

    monkeypatch.setattr("app.routes.cache.get_feed", mock_get_feed)
    monkeypatch.setattr("app.routes.cache.set_feed", mock_set_feed)
    monkeypatch.setattr("app.routes.clients.get_trending_videos", mock_get_trending)
    monkeypatch.setattr("app.routes.clients.rank_videos", mock_rank)

    with TestClient(app) as client:
        resp = client.get("/feed/user-123")

    assert resp.status_code == 200
    assert resp.json()["source"] == "personalized_ranking"
    assert set_feed_called, "set_feed should be attempted even when Redis was unavailable on read"


def test_feed_returns_502_when_video_service_unavailable(monkeypatch):
    """Feed returns 502 if the Video Service is unreachable (get_trending_videos raises)."""
    async def mock_get_feed(user_id):
        return None

    async def mock_get_trending_fails():
        raise httpx.ConnectError("video service down")

    monkeypatch.setattr("app.routes.cache.get_feed", mock_get_feed)
    monkeypatch.setattr("app.routes.clients.get_trending_videos", mock_get_trending_fails)

    with TestClient(app) as client:
        resp = client.get("/feed/user-123")

    assert resp.status_code == 502
