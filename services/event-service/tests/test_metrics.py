import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from prometheus_client import REGISTRY

from app.main import app
from app.database import get_db
from app.routes import _publish_and_record


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


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


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("event_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("event_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    val = _counter("event_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    db = _committed_db()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch("app.routes.publisher.publish_event", new_callable=AsyncMock):
            with TestClient(app) as client:
                client.post("/events", json={
                    "user_id": "u1", "video_id": "v1", "event_type": "like", "idempotency_key": "k1",
                })
    finally:
        app.dependency_overrides.clear()
    template = _counter("event_request_total", {"method": "POST", "route": "/events", "status": "201"})
    raw = _counter("event_request_total", {"method": "POST", "route": "/events/something", "status": "201"})
    assert template is not None
    assert raw is None


def test_ingest_counter_increments_on_new_event():
    db = _committed_db()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch("app.routes.publisher.publish_event", new_callable=AsyncMock):
            with TestClient(app) as client:
                before = _counter("event_ingest_total") or 0.0
                client.post("/events", json={
                    "user_id": "u1", "video_id": "v1", "event_type": "like", "idempotency_key": "k2",
                })
                after = _counter("event_ingest_total") or 0.0
    finally:
        app.dependency_overrides.clear()
    assert after - before == 1.0


def test_duplicate_counter_increments_on_duplicate_event():
    db = _duplicate_db()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            before = _counter("event_duplicate_total") or 0.0
            client.post("/events", json={
                "user_id": "u1", "video_id": "v1", "event_type": "like", "idempotency_key": "k-dup",
            })
            after = _counter("event_duplicate_total") or 0.0
    finally:
        app.dependency_overrides.clear()
    assert after - before == 1.0


def test_publish_success_counter_increments_when_publish_succeeds():
    event_data = {"event_id": "e1", "user_id": "u1", "video_id": "v1", "event_type": "like"}
    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock):
        before = _counter("event_publish_success_total") or 0.0
        asyncio.run(_publish_and_record(event_data))
        after = _counter("event_publish_success_total") or 0.0
    assert after - before == 1.0


def test_publish_failure_counter_increments_when_publish_fails():
    event_data = {"event_id": "e1", "user_id": "u1", "video_id": "v1", "event_type": "like"}
    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock, side_effect=Exception("broker down")):
        before = _counter("event_publish_failure_total") or 0.0
        asyncio.run(_publish_and_record(event_data))
        after = _counter("event_publish_failure_total") or 0.0
    assert after - before == 1.0


def test_publish_failure_counter_increments_when_broker_not_connected():
    event_data = {"event_id": "e1", "user_id": "u1", "video_id": "v1", "event_type": "like"}
    # In test env, publisher._exchange is None → publish_event raises RuntimeError
    before = _counter("event_publish_failure_total") or 0.0
    asyncio.run(_publish_and_record(event_data))
    after = _counter("event_publish_failure_total") or 0.0
    assert after - before == 1.0
