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
