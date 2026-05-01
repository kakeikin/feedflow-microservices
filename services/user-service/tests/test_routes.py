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


def _user_exists():
    r = MagicMock()
    r.scalar_one_or_none.return_value = MagicMock(id="u1")
    return r


def _no_user():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _interest_exists(score: float):
    r = MagicMock()
    m = MagicMock()
    m.score = score
    r.scalar_one_or_none.return_value = m
    return r


def _no_interest():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _final_interest(tag: str, score: float):
    r = MagicMock()
    m = MagicMock()
    m.tag = tag
    m.score = score
    r.scalar_one.return_value = m
    return r


def test_patch_interest_applies_positive_delta():
    """Existing row score=0.5 + delta=0.1 → 0.6 returned."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _interest_exists(0.5),
        MagicMock(),                   # upsert (no return)
        _final_interest("ai", 0.6),    # re-fetch
    ])
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.1})
        assert resp.status_code == 200
        assert resp.json() == {"tag": "ai", "score": 0.6}


def test_patch_interest_clamped_at_1():
    """Score 0.95 + delta 0.2 → clamped to 1.0."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _interest_exists(0.95),
        MagicMock(),
        _final_interest("ai", 1.0),
    ])
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.2})
        assert resp.status_code == 200
        assert resp.json()["score"] == 1.0


def test_patch_interest_clamped_at_0():
    """Score 0.05 + delta -0.2 → clamped to 0.0."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _interest_exists(0.05),
        MagicMock(),
        _final_interest("ai", 0.0),
    ])
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": -0.2})
        assert resp.status_code == 200
        assert resp.json()["score"] == 0.0


def test_patch_interest_no_row_positive_delta_creates():
    """No existing row, delta > 0 → creates row."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _no_interest(),
        MagicMock(),
        _final_interest("ai", 0.1),
    ])
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.1})
        assert resp.status_code == 200
        assert resp.json() == {"tag": "ai", "score": 0.1}
        db.commit.assert_awaited_once()


def test_patch_interest_no_row_negative_delta_no_write():
    """No existing row, delta <= 0 → returns score=0.0 without any DB write."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _no_interest(),
    ])
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": -0.08})
        assert resp.status_code == 200
        assert resp.json() == {"tag": "ai", "score": 0.0}
        db.commit.assert_not_awaited()


def test_patch_interest_no_row_zero_delta_no_write():
    """No existing row, delta == 0 → returns score=0.0 without any DB write."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _no_interest(),
    ])
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.0})
        assert resp.status_code == 200
        assert resp.json() == {"tag": "ai", "score": 0.0}
        db.commit.assert_not_awaited()


def test_patch_interest_user_not_found():
    """User missing → 404."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_no_user())
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.1})
        assert resp.status_code == 404
