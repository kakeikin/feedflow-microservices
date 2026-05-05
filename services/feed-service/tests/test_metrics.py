from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("feed_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("feed_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_latency_histogram_count_increments_on_request():
    with TestClient(app) as client:
        before = _counter("feed_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
        client.get("/health")
        after = _counter("feed_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    # If middleware did NOT exclude /metrics, route="/metrics" would be recorded
    val = _counter("feed_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    with patch("app.routes.cache.get_feed", new_callable=AsyncMock, return_value=None), \
         patch("app.routes.clients.get_trending_videos", new_callable=AsyncMock, return_value=[]), \
         patch("app.routes.cache.set_feed", new_callable=AsyncMock):
        with TestClient(app) as client:
            client.get("/feed/specific-user-abc")
    template = _counter("feed_request_total", {"method": "GET", "route": "/feed/{user_id}", "status": "200"})
    raw = _counter("feed_request_total", {"method": "GET", "route": "/feed/specific-user-abc", "status": "200"})
    assert template is not None
    assert raw is None


def test_cache_hit_counter_increments():
    cached = [{"video_id": "v1", "score": 0.9, "reason": "test"}]
    with patch("app.routes.cache.get_feed", new_callable=AsyncMock, return_value=cached):
        with TestClient(app) as client:
            before = _counter("feed_cache_hit_total") or 0.0
            client.get("/feed/user-hit")
            after = _counter("feed_cache_hit_total") or 0.0
    assert after - before == 1.0


def test_cache_miss_counter_increments():
    with patch("app.routes.cache.get_feed", new_callable=AsyncMock, return_value=None), \
         patch("app.routes.clients.get_trending_videos", new_callable=AsyncMock, return_value=[]), \
         patch("app.routes.clients.rank_videos", new_callable=AsyncMock, return_value=[]), \
         patch("app.routes.cache.set_feed", new_callable=AsyncMock):
        with TestClient(app) as client:
            before = _counter("feed_cache_miss_total") or 0.0
            client.get("/feed/user-miss")
            after = _counter("feed_cache_miss_total") or 0.0
    assert after - before == 1.0


def test_fallback_counter_increments_on_ranking_failure():
    with patch("app.routes.cache.get_feed", new_callable=AsyncMock, return_value=None), \
         patch("app.routes.clients.get_trending_videos", new_callable=AsyncMock, return_value=[{"id": "v1"}]), \
         patch("app.routes.clients.rank_videos", new_callable=AsyncMock, side_effect=Exception("ranking down")):
        with TestClient(app) as client:
            before = _counter("feed_fallback_total") or 0.0
            client.get("/feed/user-fallback")
            after = _counter("feed_fallback_total") or 0.0
    assert after - before == 1.0


def test_request_total_records_500_on_unhandled_exception():
    with patch("app.routes.cache.get_feed", new_callable=AsyncMock, side_effect=RuntimeError("unexpected")):
        with TestClient(app, raise_server_exceptions=False) as client:
            before = _counter("feed_request_total", {"method": "GET", "route": "/feed/{user_id}", "status": "500"}) or 0.0
            client.get("/feed/user-exc")
            after = _counter("feed_request_total", {"method": "GET", "route": "/feed/{user_id}", "status": "500"}) or 0.0
    assert after - before == 1.0
