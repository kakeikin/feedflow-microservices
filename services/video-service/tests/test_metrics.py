from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app
from app.database import get_db


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("video_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("video_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_latency_histogram_count_increments():
    with TestClient(app) as client:
        before = _counter("video_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
        client.get("/health")
        after = _counter("video_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    val = _counter("video_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    stats_mock = MagicMock()
    stats_mock.views = 0
    stats_mock.likes = 0
    stats_mock.skips = 0
    stats_mock.completion_rate = 0.0

    video_mock = MagicMock()
    video_mock.id = "v-123"
    video_mock.title = "Test"
    video_mock.creator_id = "c1"
    video_mock.tags = []
    video_mock.duration_seconds = 60
    video_mock.created_at = MagicMock()
    video_mock.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    video_mock.stats = stats_mock

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = video_mock

    db = MagicMock()
    db.execute = AsyncMock(return_value=result_mock)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            resp = client.get("/videos/v-123")
            assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()

    template = _counter("video_request_total", {"method": "GET", "route": "/videos/{video_id}", "status": "200"})
    raw = _counter("video_request_total", {"method": "GET", "route": "/videos/v-123", "status": "200"})
    assert template is not None
    assert raw is None


def test_request_total_records_500_on_unhandled_exception():
    async def _exploding_get_db():
        raise RuntimeError("boom")
        yield  # pragma: no cover — yield is required so Python marks this as an async generator; the raise fires before it is reached

    app.dependency_overrides[get_db] = _exploding_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            before = _counter("video_request_total", {"method": "GET", "route": "/videos/{video_id}", "status": "500"}) or 0.0
            client.get("/videos/v-boom")
            after = _counter("video_request_total", {"method": "GET", "route": "/videos/{video_id}", "status": "500"}) or 0.0
    finally:
        app.dependency_overrides.clear()
    assert after - before == 1.0
