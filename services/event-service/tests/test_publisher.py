import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch


def test_publish_event_sends_correct_body_and_routing_key():
    """publish_event() calls exchange.publish with correct JSON body and routing key."""
    from app import publisher

    mock_exchange = AsyncMock()
    publisher._exchange = mock_exchange

    event_data = {
        "event_id": "evt-1",
        "user_id": "u-1",
        "video_id": "v-1",
        "event_type": "like",
        "completion_rate": None,
        "watch_time_seconds": None,
    }

    asyncio.run(publisher.publish_event(event_data))

    mock_exchange.publish.assert_awaited_once()
    call_args = mock_exchange.publish.await_args
    message = call_args[0][0]
    routing_key = call_args[1]["routing_key"]

    assert routing_key == "user.interaction"
    body = json.loads(message.body)
    assert body["event_id"] == "evt-1"
    assert body["event_type"] == "like"
    assert body["completion_rate"] is None

    publisher._exchange = None  # cleanup


def test_publish_event_no_op_when_not_connected():
    """publish_event() logs and returns without raising when exchange is None."""
    from app import publisher
    publisher._exchange = None

    event_data = {"event_id": "evt-1", "user_id": "u-1", "video_id": "v-1",
                  "event_type": "like", "completion_rate": None, "watch_time_seconds": None}

    # Should not raise
    asyncio.run(publisher.publish_event(event_data))


def test_publish_event_logs_and_swallows_exception():
    """publish_event() catches exceptions from exchange.publish and does not re-raise."""
    from app import publisher

    mock_exchange = AsyncMock()
    mock_exchange.publish.side_effect = Exception("broker unreachable")
    publisher._exchange = mock_exchange

    event_data = {"event_id": "evt-2", "user_id": "u-1", "video_id": "v-1",
                  "event_type": "watch", "completion_rate": None, "watch_time_seconds": None}

    # Must not raise
    asyncio.run(publisher.publish_event(event_data))

    publisher._exchange = None  # cleanup
