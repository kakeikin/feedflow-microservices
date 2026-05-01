import time
import uuid
import httpx

USER_SERVICE = "http://localhost:8001"
VIDEO_SERVICE = "http://localhost:8002"
EVENT_SERVICE = "http://localhost:8003"


def poll_until(condition_fn, timeout: float = 5.0, interval: float = 0.25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


def _create_user() -> str:
    resp = httpx.post(
        f"{USER_SERVICE}/users",
        json={"email": f"pipeline-{uuid.uuid4()}@example.com", "display_name": "Pipeline Tester"},
        timeout=5.0,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_video(creator_id: str, tags: list[str]) -> str:
    resp = httpx.post(
        f"{VIDEO_SERVICE}/videos",
        json={"title": f"Test Video {uuid.uuid4()}", "creator_id": creator_id, "tags": tags, "duration_seconds": 60},
        timeout=5.0,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _post_event(user_id: str, video_id: str, event_type: str, completion_rate: float | None = None) -> dict:
    resp = httpx.post(
        f"{EVENT_SERVICE}/events",
        json={
            "user_id": user_id,
            "video_id": video_id,
            "event_type": event_type,
            "completion_rate": completion_rate,
            "idempotency_key": str(uuid.uuid4()),
        },
        timeout=5.0,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _get_interest_score(user_id: str, tag: str) -> float | None:
    resp = httpx.get(f"{USER_SERVICE}/users/{user_id}/interests", timeout=5.0)
    assert resp.status_code == 200
    for interest in resp.json():
        if interest["tag"] == tag:
            return interest["score"]
    return None


def _get_video_stats(video_id: str) -> dict:
    resp = httpx.get(f"{VIDEO_SERVICE}/videos/{video_id}", timeout=5.0)
    assert resp.status_code == 200
    return resp.json()["stats"]


def test_like_event_increases_user_interest_score():
    """POST like event → user interest score for video's tags increases (polled)."""
    user_id = _create_user()
    video_id = _create_video(user_id, tags=["ai", "backend"])

    result = _post_event(user_id, video_id, event_type="like")
    assert result["status"] == "created"

    found = poll_until(
        lambda: _get_interest_score(user_id, "ai") is not None,
        timeout=5.0,
    )
    assert found, "Interest score for tag 'ai' never appeared within 5s"

    score = _get_interest_score(user_id, "ai")
    assert abs(score - 0.10) < 0.01, f"Expected interest score ≈ 0.10 (like delta), got {score}"


def test_watch_event_does_not_increment_views():
    """POST watch event → video views remain unchanged (polled wait, then assert)."""
    user_id = _create_user()
    video_id = _create_video(user_id, tags=["ml"])

    initial_stats = _get_video_stats(video_id)
    initial_views = initial_stats["views"]

    _post_event(user_id, video_id, event_type="watch")
    # Send a like on the same video to anchor pipeline liveness: poll until interest appears,
    # confirming the pipeline was active for this video during the assertion window.
    _post_event(user_id, video_id, event_type="like")
    pipeline_live = poll_until(
        lambda: _get_interest_score(user_id, "ml") is not None,
        timeout=5.0,
    )
    assert pipeline_live, "Pipeline did not process like event within 5s — cannot assert views unchanged"

    stats = _get_video_stats(video_id)
    assert stats["views"] == initial_views, (
        f"views incremented from {initial_views} to {stats['views']} after watch event — must not increment"
    )


def test_complete_event_increments_views_and_updates_completion_rate():
    """POST complete event → views +1 and completion_rate updated (polled)."""
    user_id = _create_user()
    video_id = _create_video(user_id, tags=["science"])

    initial_stats = _get_video_stats(video_id)
    initial_views = initial_stats["views"]

    _post_event(user_id, video_id, event_type="complete", completion_rate=0.8)

    incremented = poll_until(
        lambda: _get_video_stats(video_id)["views"] > initial_views,
        timeout=5.0,
    )
    assert incremented, f"views never incremented above {initial_views} within 5s"

    stats = _get_video_stats(video_id)
    assert stats["views"] == initial_views + 1
    # completion_rate = (0.0 * 0 + 0.8) / (0 + 1) = 0.8 (first ever complete on fresh video)
    assert abs(stats["completion_rate"] - 0.8) < 0.01, (
        f"Expected completion_rate ≈ 0.8, got {stats['completion_rate']}"
    )


def test_duplicate_event_processed_only_once():
    """Second submission with same idempotency_key → duplicate_ignored → interest incremented once only."""
    user_id = _create_user()
    video_id = _create_video(user_id, tags=["duplicate-test"])
    idempotency_key = str(uuid.uuid4())

    payload = {
        "user_id": user_id,
        "video_id": video_id,
        "event_type": "like",
        "idempotency_key": idempotency_key,
    }

    first = httpx.post(f"{EVENT_SERVICE}/events", json=payload, timeout=5.0)
    assert first.status_code == 201
    assert first.json()["status"] == "created"

    second = httpx.post(f"{EVENT_SERVICE}/events", json=payload, timeout=5.0)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate_ignored"

    # Wait for the single like to be processed
    poll_until(
        lambda: _get_interest_score(user_id, "duplicate-test") is not None,
        timeout=5.0,
    )

    # Wait an additional 2s to ensure no double-processing
    time.sleep(2.0)

    score = _get_interest_score(user_id, "duplicate-test")
    assert score is not None
    # like delta = +0.10; if processed twice = 0.20
    assert abs(score - 0.10) < 0.01, (
        f"Expected score ≈ 0.10 (processed once), got {score} (may have been processed twice)"
    )
