import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.database import get_db


def _committed_db():
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _duplicate_db():
    db = MagicMock()
    exc = IntegrityError(None, None, Exception("duplicate"))
    exc.orig = MagicMock()
    exc.orig.pgcode = "23505"
    db.commit = AsyncMock(side_effect=exc)
    db.rollback = AsyncMock()
    return db


def test_created_event_enqueues_background_task():
    """A newly created event (status=created) triggers publish_event via BackgroundTask."""
    db = _committed_db()

    async def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db

    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock) as mock_publish:
        with TestClient(app) as client:
            resp = client.post("/events", json={
                "user_id": "u-1",
                "video_id": "v-1",
                "event_type": "like",
                "idempotency_key": "key-001",
            })
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"
        mock_publish.assert_awaited_once()
        call_kwargs = mock_publish.await_args[0][0]
        assert call_kwargs["event_type"] == "like"
        assert call_kwargs["user_id"] == "u-1"

    app.dependency_overrides.clear()


def test_duplicate_event_does_not_enqueue_background_task():
    """A duplicate event (status=duplicate_ignored) must NOT call publish_event."""
    db = _duplicate_db()

    async def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db

    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock) as mock_publish:
        with TestClient(app) as client:
            resp = client.post("/events", json={
                "user_id": "u-1",
                "video_id": "v-1",
                "event_type": "like",
                "idempotency_key": "key-dup",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "duplicate_ignored"
        mock_publish.assert_not_awaited()

    app.dependency_overrides.clear()
