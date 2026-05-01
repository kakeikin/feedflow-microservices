import pytest
from contextlib import contextmanager
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.database import get_db


@contextmanager
def _make_client(mock_session):
    async def override_get_db():
        yield mock_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _video_exists():
    r = MagicMock()
    r.scalar_one_or_none.return_value = MagicMock(id="v1")
    return r


def _no_video():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _stats_row(views=10, likes=2, skips=1, completion_rate=0.5):
    row = MagicMock()
    row.views = views
    row.likes = likes
    row.skips = skips
    row.completion_rate = completion_rate
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def test_patch_stats_applies_likes_delta():
    """likes_delta=+1 → response has incremented likes."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_video_exists(), _stats_row(views=5, likes=3, skips=1, completion_rate=0.4)])
    with _make_client(db) as client:
        resp = client.patch("/videos/v1/stats", json={
            "views_delta": 0, "likes_delta": 1, "skips_delta": 0, "completion_rate_sample": None
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["likes"] == 3
        assert body["views"] == 5


def test_patch_stats_complete_event():
    """views_delta=1, completion_rate_sample=0.8 → response reflects updated values."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _video_exists(),
        _stats_row(views=11, likes=0, skips=0, completion_rate=0.84),
    ])
    with _make_client(db) as client:
        resp = client.patch("/videos/v1/stats", json={
            "views_delta": 1, "likes_delta": 0, "skips_delta": 0, "completion_rate_sample": 0.8
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["views"] == 11
        assert body["completion_rate"] == pytest.approx(0.84)


def test_patch_stats_video_not_found():
    """Video missing → 404."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_no_video())
    with _make_client(db) as client:
        resp = client.patch("/videos/v1/stats", json={
            "views_delta": 0, "likes_delta": 1, "skips_delta": 0, "completion_rate_sample": None
        })
        assert resp.status_code == 404


def test_patch_stats_no_completion_rate_when_null():
    """completion_rate_sample=null → response completion_rate unchanged."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _video_exists(),
        _stats_row(views=5, likes=1, skips=0, completion_rate=0.5),
    ])
    with _make_client(db) as client:
        resp = client.patch("/videos/v1/stats", json={
            "views_delta": 0, "likes_delta": 1, "skips_delta": 0, "completion_rate_sample": None
        })
        assert resp.status_code == 200
        assert resp.json()["completion_rate"] == 0.5
