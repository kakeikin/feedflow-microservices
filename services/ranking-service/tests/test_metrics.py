from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("ranking_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("ranking_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_latency_histogram_count_increments():
    with TestClient(app) as client:
        before = _counter("ranking_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
        client.get("/health")
        after = _counter("ranking_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    val = _counter("ranking_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    with patch("app.routes.clients.get_user_interests", new_callable=AsyncMock, return_value=[]), \
         patch("app.routes.clients.get_video", new_callable=AsyncMock, return_value=None):
        with TestClient(app) as client:
            client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v-missing"]})
    template = _counter("ranking_request_total", {"method": "POST", "route": "/rank", "status": "200"})
    raw = _counter("ranking_request_total", {"method": "POST", "route": "/rank/something", "status": "200"})
    assert template is not None
    assert raw is None


def test_candidate_count_histogram_observes_resolved_count():
    video = {
        "id": "v1", "tags": ["tech"], "created_at": "2026-04-01T00:00:00Z",
        "stats": {"likes": 5, "skips": 0, "completion_rate": 0.8},
    }
    with patch("app.routes.clients.get_user_interests", new_callable=AsyncMock, return_value=[{"tag": "tech", "score": 0.9}]), \
         patch("app.routes.clients.get_video", new_callable=AsyncMock, return_value=video):
        with TestClient(app) as client:
            before = _counter("ranking_candidate_count_count") or 0.0
            client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1"]})
            after = _counter("ranking_candidate_count_count") or 0.0
    assert after - before == 1.0


def test_upstream_error_counter_increments_when_video_returns_none():
    with patch("app.routes.clients.get_user_interests", new_callable=AsyncMock, return_value=[]), \
         patch("app.routes.clients.get_video", new_callable=AsyncMock, return_value=None):
        with TestClient(app) as client:
            before = _counter("ranking_upstream_error_total") or 0.0
            client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v-missing"]})
            after = _counter("ranking_upstream_error_total") or 0.0
    assert after - before == 1.0


def test_request_total_records_500_on_unhandled_exception():
    with patch("app.routes.clients.get_user_interests", new_callable=AsyncMock, side_effect=RuntimeError("unexpected")):
        with TestClient(app, raise_server_exceptions=False) as client:
            before = _counter("ranking_request_total", {"method": "POST", "route": "/rank", "status": "500"}) or 0.0
            client.post("/rank", json={"user_id": "u1", "candidate_video_ids": []})
            after = _counter("ranking_request_total", {"method": "POST", "route": "/rank", "status": "500"}) or 0.0
    assert after - before == 1.0
