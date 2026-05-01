import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


VIDEO_RESPONSE = {
    "id": "v-1",
    "title": "Test Video",
    "creator_id": "u-1",
    "tags": ["ai", "ml"],
    "duration_seconds": 90,
    "stats": {"views": 5, "likes": 1, "skips": 0, "completion_rate": 0.5},
}


def _make_message(event_type="like", event_id="evt-1", user_id="u-1", video_id="v-1",
                  completion_rate=None, retry_count=0):
    msg = MagicMock()
    msg.body = json.dumps({
        "event_id": event_id,
        "user_id": user_id,
        "video_id": video_id,
        "event_type": event_type,
        "completion_rate": completion_rate,
        "watch_time_seconds": None,
    }).encode()
    msg.headers = {"x-retry-count": retry_count} if retry_count else {}
    msg.ack = AsyncMock()
    return msg


def _make_exchange():
    ex = AsyncMock()
    ex.publish = AsyncMock()
    return ex


def _make_default_exchange():
    ex = AsyncMock()
    ex.publish = AsyncMock()
    return ex


def _http_status_error(status_code: int):
    response = MagicMock()
    response.status_code = status_code
    return httpx.HTTPStatusError("error", request=MagicMock(), response=response)


@patch("app.consumer.clients.patch_user_interest", new_callable=AsyncMock)
@patch("app.consumer.clients.patch_video_stats", new_callable=AsyncMock)
@patch("app.consumer.clients.get_video", new_callable=AsyncMock)
def test_like_event_patches_stats_and_interests(mock_get_video, mock_patch_stats, mock_patch_interest):
    """like event: likes_delta=+1, interest_delta=+0.10 per tag, ACK."""
    mock_get_video.return_value = VIDEO_RESPONSE
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()
    message = _make_message(event_type="like")

    from app import consumer
    asyncio.run(consumer.handle_message(message, exchange, default_exchange))

    mock_patch_stats.assert_awaited_once_with("v-1", {
        "views_delta": 0,
        "likes_delta": 1,
        "skips_delta": 0,
        "completion_rate_sample": None,
    })
    assert mock_patch_interest.await_count == 2
    mock_patch_interest.assert_any_await("u-1", "ai", pytest.approx(0.10))
    mock_patch_interest.assert_any_await("u-1", "ml", pytest.approx(0.10))
    message.ack.assert_awaited_once()


@patch("app.consumer.clients.patch_user_interest", new_callable=AsyncMock)
@patch("app.consumer.clients.patch_video_stats", new_callable=AsyncMock)
@patch("app.consumer.clients.get_video", new_callable=AsyncMock)
def test_watch_event_skips_stats_patch(mock_get_video, mock_patch_stats, mock_patch_interest):
    """watch event: all stat deltas are zero → patch_video_stats NOT called."""
    mock_get_video.return_value = VIDEO_RESPONSE
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()
    message = _make_message(event_type="watch")

    from app import consumer
    asyncio.run(consumer.handle_message(message, exchange, default_exchange))

    mock_patch_stats.assert_not_awaited()
    assert mock_patch_interest.await_count == 2
    message.ack.assert_awaited_once()


@patch("app.consumer.clients.patch_user_interest", new_callable=AsyncMock)
@patch("app.consumer.clients.patch_video_stats", new_callable=AsyncMock)
@patch("app.consumer.clients.get_video", new_callable=AsyncMock)
def test_complete_event_passes_completion_rate(mock_get_video, mock_patch_stats, mock_patch_interest):
    """complete event: views_delta=1, completion_rate_sample passed from message."""
    mock_get_video.return_value = VIDEO_RESPONSE
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()
    message = _make_message(event_type="complete", completion_rate=0.8)

    from app import consumer
    asyncio.run(consumer.handle_message(message, exchange, default_exchange))

    mock_patch_stats.assert_awaited_once_with("v-1", {
        "views_delta": 1,
        "likes_delta": 0,
        "skips_delta": 0,
        "completion_rate_sample": 0.8,
    })
    message.ack.assert_awaited_once()


@patch("app.consumer.clients.get_video", new_callable=AsyncMock)
def test_video_not_found_acks_without_retry(mock_get_video):
    """404 from get_video → non-retryable: ACK, no republish."""
    mock_get_video.side_effect = _http_status_error(404)
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()
    message = _make_message()

    from app import consumer
    asyncio.run(consumer.handle_message(message, exchange, default_exchange))

    message.ack.assert_awaited_once()
    exchange.publish.assert_not_awaited()
    default_exchange.publish.assert_not_awaited()


@patch("app.consumer.clients.get_video", new_callable=AsyncMock)
def test_non_404_4xx_from_video_service_acks_without_retry(mock_get_video):
    """Non-404 4xx (e.g. 403) from get_video → non-retryable: ACK, no republish."""
    mock_get_video.side_effect = _http_status_error(403)
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()
    message = _make_message()

    from app import consumer
    asyncio.run(consumer.handle_message(message, exchange, default_exchange))

    message.ack.assert_awaited_once()
    exchange.publish.assert_not_awaited()
    default_exchange.publish.assert_not_awaited()


@patch("app.consumer.clients.get_video", new_callable=AsyncMock)
def test_5xx_from_video_service_triggers_retry(mock_get_video):
    """5xx from get_video → transient: republish with x-retry-count=1, ACK original."""
    mock_get_video.side_effect = _http_status_error(503)
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()
    message = _make_message(retry_count=0)

    from app import consumer
    asyncio.run(consumer.handle_message(message, exchange, default_exchange))

    exchange.publish.assert_awaited_once()
    call_args = exchange.publish.await_args
    retry_msg = call_args[0][0]
    assert retry_msg.headers["x-retry-count"] == 1
    assert call_args[1]["routing_key"] == "user.interaction"
    message.ack.assert_awaited_once()


@patch("app.consumer.clients.get_video", new_callable=AsyncMock)
def test_exhausted_retries_route_to_dlq(mock_get_video):
    """After 3 retries (x-retry-count=3), message goes to DLQ via default exchange."""
    mock_get_video.side_effect = _http_status_error(500)
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()
    message = _make_message(retry_count=3)

    from app import consumer
    asyncio.run(consumer.handle_message(message, exchange, default_exchange))

    default_exchange.publish.assert_awaited_once()
    call_args = default_exchange.publish.await_args
    assert call_args[1]["routing_key"] == "feature.update.dlq"
    exchange.publish.assert_not_awaited()
    message.ack.assert_awaited_once()


def test_invalid_json_acks_without_retry():
    """Malformed JSON body → non-retryable: ACK, no republish."""
    msg = MagicMock()
    msg.body = b"not valid json {"
    msg.headers = {}
    msg.ack = AsyncMock()
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()

    from app import consumer
    asyncio.run(consumer.handle_message(msg, exchange, default_exchange))

    msg.ack.assert_awaited_once()
    exchange.publish.assert_not_awaited()


def test_unknown_event_type_acks_without_retry():
    """Unknown event_type → non-retryable: ACK, no republish."""
    msg = MagicMock()
    msg.body = json.dumps({
        "event_id": "e1", "user_id": "u1", "video_id": "v1",
        "event_type": "explode", "completion_rate": None, "watch_time_seconds": None
    }).encode()
    msg.headers = {}
    msg.ack = AsyncMock()
    exchange = _make_exchange()
    default_exchange = _make_default_exchange()

    from app import consumer
    asyncio.run(consumer.handle_message(msg, exchange, default_exchange))

    msg.ack.assert_awaited_once()
    exchange.publish.assert_not_awaited()


@patch("app.consumer.clients.patch_user_interest", new_callable=AsyncMock)
@patch("app.consumer.clients.patch_video_stats", new_callable=AsyncMock)
@patch("app.consumer.clients.get_video", new_callable=AsyncMock)
def test_user_not_found_acks_stops_remaining_interests(mock_get_video, mock_patch_stats, mock_patch_interest):
    """404 from patch_user_interest → non-retryable: ACK, stops remaining interest patches."""
    mock_get_video.return_value = VIDEO_RESPONSE  # has tags ["ai", "ml"]
    mock_patch_stats.return_value = None
    mock_patch_interest.side_effect = [_http_status_error(404)]  # fails on first tag

    exchange = _make_exchange()
    default_exchange = _make_default_exchange()
    message = _make_message(event_type="like")

    from app import consumer
    asyncio.run(consumer.handle_message(message, exchange, default_exchange))

    # Should stop after first 404 — only 1 call, not 2
    assert mock_patch_interest.await_count == 1
    message.ack.assert_awaited_once()
    exchange.publish.assert_not_awaited()
