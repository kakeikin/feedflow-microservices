import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from prometheus_client import REGISTRY

from app.consumer import handle_message


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def _make_message(body: dict, retry_count: int = 0) -> MagicMock:
    msg = MagicMock()
    msg.body = json.dumps(body).encode()
    msg.headers = {"x-retry-count": retry_count}
    msg.content_type = "application/json"
    msg.ack = AsyncMock()
    return msg


def _make_exchanges():
    exchange = MagicMock()
    exchange.publish = AsyncMock()
    default_exchange = MagicMock()
    default_exchange.publish = AsyncMock()
    return exchange, default_exchange


VALID_BODY = {
    "event_id": "e1",
    "user_id": "u1",
    "video_id": "v1",
    "event_type": "like",
    "completion_rate": None,
}

VIDEO_DATA = {
    "id": "v1", "tags": ["tech"], "created_at": "2026-01-01T00:00:00Z",
    "stats": {"views": 10, "likes": 5, "skips": 1, "completion_rate": 0.7},
}


def run(coro):
    return asyncio.run(coro)


def test_processed_total_increments_on_successful_message():
    msg = _make_message(VALID_BODY)
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, return_value=VIDEO_DATA), \
         patch("app.consumer.clients.patch_video_stats", new_callable=AsyncMock), \
         patch("app.consumer.clients.patch_user_interest", new_callable=AsyncMock):
        before = _counter("worker_message_processed_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_message_processed_total") or 0.0
    assert after - before == 1.0


def test_processed_total_does_not_increment_on_retry():
    msg = _make_message(VALID_BODY)
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=httpx.ConnectError("transient")):
        before = _counter("worker_message_processed_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_message_processed_total") or 0.0
    assert after - before == 0.0


def test_retry_total_increments_when_message_republished():
    msg = _make_message(VALID_BODY, retry_count=0)
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=httpx.ConnectError("transient")):
        before = _counter("worker_message_retry_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_message_retry_total") or 0.0
    assert after - before == 1.0


def test_dlq_total_increments_when_max_retries_exceeded():
    msg = _make_message(VALID_BODY, retry_count=3)  # MAX_RETRIES = 3
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=httpx.ConnectError("transient")):
        before = _counter("worker_message_dlq_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_message_dlq_total") or 0.0
    assert after - before == 1.0


def test_failed_total_increments_when_max_retries_exceeded():
    msg = _make_message(VALID_BODY, retry_count=3)  # MAX_RETRIES = 3
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=httpx.ConnectError("transient")):
        before = _counter("worker_message_failed_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_message_failed_total") or 0.0
    assert after - before == 1.0


def test_failed_total_does_not_increment_on_first_retry():
    msg = _make_message(VALID_BODY, retry_count=0)
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=httpx.ConnectError("transient")):
        before = _counter("worker_message_failed_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_message_failed_total") or 0.0
    assert after - before == 0.0


def test_latency_histogram_count_increments_on_any_message():
    msg = _make_message(VALID_BODY)
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, return_value=VIDEO_DATA), \
         patch("app.consumer.clients.patch_video_stats", new_callable=AsyncMock), \
         patch("app.consumer.clients.patch_user_interest", new_callable=AsyncMock):
        before = _counter("worker_processing_latency_seconds_count") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_processing_latency_seconds_count") or 0.0
    assert after - before == 1.0
