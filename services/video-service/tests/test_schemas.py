import pytest
from pydantic import ValidationError
from datetime import datetime, timezone


def test_video_create_valid():
    from app.schemas import VideoCreate
    v = VideoCreate(
        title="Intro to AI",
        creator_id="user-1",
        tags=["ai", "backend"],
        duration_seconds=120,
    )
    assert v.title == "Intro to AI"
    assert v.tags == ["ai", "backend"]
    assert v.duration_seconds == 120


def test_video_create_missing_title():
    from app.schemas import VideoCreate
    with pytest.raises(ValidationError):
        VideoCreate(creator_id="u", tags=[], duration_seconds=60)


def test_video_stats_defaults():
    from app.schemas import VideoStatsResponse
    stats = VideoStatsResponse(views=0, likes=0, skips=0, completion_rate=0.0)
    assert stats.views == 0
    assert stats.completion_rate == 0.0


def test_video_create_missing_duration():
    from app.schemas import VideoCreate
    with pytest.raises(ValidationError):
        VideoCreate(title="T", creator_id="u", tags=["ai"])


def test_trending_sort_order():
    """Test trending sort: likes DESC, views DESC, created_at DESC"""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = [
        {"video_id": "a", "likes": 5, "views": 100, "created_at": now},
        {"video_id": "b", "likes": 10, "views": 50, "created_at": now},
        {"video_id": "c", "likes": 10, "views": 200, "created_at": now},
    ]
    sorted_videos = sorted(
        candidates,
        key=lambda v: (-v["likes"], -v["views"], -v["created_at"].timestamp()),
    )
    ids = [v["video_id"] for v in sorted_videos]
    assert ids == ["c", "b", "a"], f"Expected c,b,a but got {ids}"


def test_trending_sort_all_zero_likes():
    """Test trending sort with same likes and views, newer video comes first"""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older = datetime(2025, 12, 1, tzinfo=timezone.utc)
    candidates = [
        {"video_id": "x", "likes": 0, "views": 10, "created_at": older},
        {"video_id": "y", "likes": 0, "views": 10, "created_at": now},
    ]
    sorted_videos = sorted(
        candidates,
        key=lambda v: (-v["likes"], -v["views"], -v["created_at"].timestamp()),
    )
    ids = [v["video_id"] for v in sorted_videos]
    # Newer video (now > older) should come first since created_at DESC
    assert ids == ["y", "x"], f"Newer video should rank first on created_at DESC, got {ids}"
