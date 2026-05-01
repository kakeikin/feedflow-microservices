import time
import uuid
import httpx

USER_SERVICE = "http://localhost:8001"
VIDEO_SERVICE = "http://localhost:8002"
EVENT_SERVICE = "http://localhost:8003"
RANKING_SERVICE = "http://localhost:8004"
FEED_SERVICE = "http://localhost:8005"


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
        json={"email": f"phase3-{uuid.uuid4()}@example.com", "display_name": "Phase3 Tester"},
        timeout=5.0,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_video(creator_id: str, tags: list[str]) -> str:
    resp = httpx.post(
        f"{VIDEO_SERVICE}/videos",
        json={
            "title": f"Phase3 Video {uuid.uuid4()}",
            "creator_id": creator_id,
            "tags": tags,
            "duration_seconds": 90,
        },
        timeout=5.0,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _post_event(
    user_id: str,
    video_id: str,
    event_type: str,
    completion_rate: float | None = None,
) -> dict:
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


def test_feed_cache_hit_on_second_request():
    """Second GET /feed/{user_id} returns source=cache_hit without calling upstream."""
    user_id = _create_user()
    _create_video(user_id, tags=["ai"])

    resp1 = httpx.get(f"{FEED_SERVICE}/feed/{user_id}", timeout=5.0)
    assert resp1.status_code == 200
    assert resp1.json()["source"] in ("personalized_ranking", "trending_fallback")
    assert len(resp1.json()["items"]) > 0, "Feed must contain at least one item for cache test to be meaningful"

    resp2 = httpx.get(f"{FEED_SERVICE}/feed/{user_id}", timeout=5.0)
    assert resp2.status_code == 200
    assert resp2.json()["source"] == "cache_hit"
    assert resp2.json()["items"] == resp1.json()["items"], (
        "Cached feed items must match the original response items"
    )


def test_events_improve_ranking_score():
    """After like + complete events, the ranking score for the video increases (polled)."""
    user_id = _create_user()
    video_id = _create_video(user_id, tags=["ai"])

    resp1 = httpx.post(
        f"{RANKING_SERVICE}/rank",
        json={"user_id": user_id, "candidate_video_ids": [video_id]},
        timeout=5.0,
    )
    assert resp1.status_code == 200
    baseline_score = resp1.json()[0]["score"]

    _post_event(user_id, video_id, "like")
    _post_event(user_id, video_id, "complete", completion_rate=1.0)

    # Poll until Feature Worker has processed both events. Both polls must complete before the
    # ranking call below: interest_processed gates the like event, views_processed gates the
    # complete event. Together they prove both async writes landed before we re-score.
    interest_processed = poll_until(
        lambda: _get_interest_score(user_id, "ai") is not None, timeout=5.0
    )
    assert interest_processed, "Timed out waiting for Feature Worker to update user interest score"

    views_processed = poll_until(
        lambda: _get_video_stats(video_id)["views"] > 0, timeout=5.0
    )
    assert views_processed, "Timed out waiting for Feature Worker to update video view count"

    resp2 = httpx.post(
        f"{RANKING_SERVICE}/rank",
        json={"user_id": user_id, "candidate_video_ids": [video_id]},
        timeout=5.0,
    )
    assert resp2.status_code == 200
    new_score = resp2.json()[0]["score"]

    assert new_score > baseline_score, (
        f"Ranking score should increase after like+complete events; "
        f"got {baseline_score} → {new_score}"
    )
