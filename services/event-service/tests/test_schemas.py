import pytest
from pydantic import ValidationError


def test_event_create_valid():
    from app.schemas import EventCreate
    event = EventCreate(
        user_id="user-1",
        video_id="video-1",
        event_type="like",
        completion_rate=0.85,
        watch_time_seconds=42,
        idempotency_key="key-001",
    )
    assert event.event_type == "like"
    assert event.completion_rate == 0.85


def test_event_type_invalid():
    from app.schemas import EventCreate
    with pytest.raises(ValidationError):
        EventCreate(
            user_id="u",
            video_id="v",
            event_type="invalid_type",
            idempotency_key="k",
        )


def test_event_type_all_valid_values():
    from app.schemas import EventCreate
    for event_type in ["watch", "like", "skip", "complete", "share", "comment"]:
        event = EventCreate(
            user_id="u",
            video_id="v",
            event_type=event_type,
            idempotency_key=f"k-{event_type}",
        )
        assert event.event_type == event_type


def test_event_optional_fields():
    from app.schemas import EventCreate
    event = EventCreate(
        user_id="u",
        video_id="v",
        event_type="like",
        idempotency_key="k",
    )
    assert event.completion_rate is None
    assert event.watch_time_seconds is None
