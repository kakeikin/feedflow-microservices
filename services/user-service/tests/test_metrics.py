from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app
from app.database import get_db


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("user_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("user_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_latency_histogram_count_increments():
    with TestClient(app) as client:
        before = _counter("user_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
        client.get("/health")
        after = _counter("user_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    val = _counter("user_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    user_mock = MagicMock()
    user_mock.id = "u-123"
    user_mock.email = "test@test.com"
    user_mock.display_name = "Test"
    user_mock.created_at = MagicMock()
    user_mock.created_at.isoformat.return_value = "2026-01-01T00:00:00"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user_mock

    db = MagicMock()
    db.execute = AsyncMock(return_value=result_mock)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            client.get("/users/u-123")
    finally:
        app.dependency_overrides.clear()

    template = _counter("user_request_total", {"method": "GET", "route": "/users/{user_id}", "status": "200"})
    raw = _counter("user_request_total", {"method": "GET", "route": "/users/u-123", "status": "200"})
    assert template is not None
    assert raw is None


def test_request_total_records_500_on_unhandled_exception():
    # Patching a FastAPI route function after registration doesn't intercept the
    # router's captured reference.  Instead, inject a DB dependency that raises
    # an unhandled RuntimeError so the middleware records status_code=500.
    async def _exploding_get_db():
        raise RuntimeError("boom")
        yield  # pragma: no cover — dead code; presence of yield makes FastAPI treat this as an async generator dependency

    app.dependency_overrides[get_db] = _exploding_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            before = _counter("user_request_total", {"method": "GET", "route": "/users/{user_id}", "status": "500"}) or 0.0
            client.get("/users/u-boom")
            after = _counter("user_request_total", {"method": "GET", "route": "/users/{user_id}", "status": "500"}) or 0.0
    finally:
        app.dependency_overrides.clear()

    assert after - before == 1.0
