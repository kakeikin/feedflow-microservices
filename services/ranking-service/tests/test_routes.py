import pytest
from starlette.testclient import TestClient
from app.main import app

USER_INTERESTS = [{"tag": "ai", "score": 0.8}]
VIDEO_BASE = {
    "id": "v1",
    "title": "AI Video",
    "tags": ["ai"],
    "duration_seconds": 90,
    "created_at": "2026-04-30T00:00:00+00:00",
    "stats": {"views": 10, "likes": 5, "skips": 1, "completion_rate": 0.75},
}


def test_rank_returns_scored_items(monkeypatch):
    """Route returns ranked items with a non-zero score using the 4-factor formula."""
    async def mock_interests(user_id):
        return USER_INTERESTS

    async def mock_video(video_id):
        return VIDEO_BASE

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)
    monkeypatch.setattr("app.routes.clients.get_video", mock_video)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1"]})

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["video_id"] == "v1"
    assert items[0]["score"] > 0.0


def test_rank_higher_completion_rate_scores_higher(monkeypatch):
    """Video with completion_rate=1.0 outranks identical video with completion_rate=0.0."""
    async def mock_interests(user_id):
        return USER_INTERESTS

    low = dict(VIDEO_BASE, id="v1", stats=dict(VIDEO_BASE["stats"], completion_rate=0.0))
    high = dict(VIDEO_BASE, id="v2", stats=dict(VIDEO_BASE["stats"], completion_rate=1.0))

    async def mock_video(video_id):
        return low if video_id == "v1" else high

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)
    monkeypatch.setattr("app.routes.clients.get_video", mock_video)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1", "v2"]})

    # Both videos have identical interest, freshness, and engagement (likes=5, skips=1,
    # so max_net_engagement=4 and engagement=1.0 for both). Only completion_quality differs.
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert items[0]["video_id"] == "v2"
    assert items[0]["score"] > items[1]["score"]


def test_rank_empty_candidates(monkeypatch):
    async def mock_interests(user_id):
        return USER_INTERESTS

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": []})

    assert resp.status_code == 200
    assert resp.json() == []


def test_rank_degrades_when_video_unavailable(monkeypatch):
    async def mock_interests(user_id):
        return USER_INTERESTS

    async def mock_video(video_id):
        return None

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)
    monkeypatch.setattr("app.routes.clients.get_video", mock_video)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1"]})

    assert resp.status_code == 200
    assert resp.json() == []


def test_rank_all_negative_engagement(monkeypatch):
    """Route returns results without crashing when all candidates have likes <= skips."""
    async def mock_interests(user_id):
        return USER_INTERESTS

    async def mock_video(video_id):
        return dict(VIDEO_BASE, stats={"views": 10, "likes": 0, "skips": 5, "completion_rate": 0.5})

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)
    monkeypatch.setattr("app.routes.clients.get_video", mock_video)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1"]})

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["score"] >= 0.0
