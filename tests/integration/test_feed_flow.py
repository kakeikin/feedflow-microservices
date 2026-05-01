import uuid
import httpx

USER_SERVICE = "http://localhost:8001"
VIDEO_SERVICE = "http://localhost:8002"
EVENT_SERVICE = "http://localhost:8003"
FEED_SERVICE = "http://localhost:8005"


def test_create_user_and_video_appears_in_trending():
    """Create a user and video; video must appear in trending."""
    user_resp = httpx.post(
        f"{USER_SERVICE}/users",
        json={"email": f"integ-{uuid.uuid4()}@example.com", "display_name": "Integ User"},
        timeout=5.0,
    )
    assert user_resp.status_code == 201, user_resp.text
    user_id = user_resp.json()["id"]

    video_resp = httpx.post(
        f"{VIDEO_SERVICE}/videos",
        json={
            "title": "Integration Test Video",
            "creator_id": user_id,
            "tags": ["ai", "backend"],
            "duration_seconds": 90,
        },
        timeout=5.0,
    )
    assert video_resp.status_code == 201, video_resp.text
    video_id = video_resp.json()["id"]

    trending_resp = httpx.get(f"{VIDEO_SERVICE}/videos/trending", timeout=5.0)
    assert trending_resp.status_code == 200
    video_ids = [v["id"] for v in trending_resp.json()]
    assert video_id in video_ids, f"Created video {video_id} not found in trending"


def test_feed_returns_ranked_items_for_user():
    """Full flow: user with interests → create video → feed returns ranked results."""
    user_resp = httpx.post(
        f"{USER_SERVICE}/users",
        json={"email": f"feed-integ-{uuid.uuid4()}@example.com", "display_name": "Feed Tester"},
        timeout=5.0,
    )
    assert user_resp.status_code == 201
    user_id = user_resp.json()["id"]

    interest_resp = httpx.post(
        f"{USER_SERVICE}/users/{user_id}/interests",
        json={"tag": "ai", "score": 0.9},
        timeout=5.0,
    )
    assert interest_resp.status_code == 201

    video_resp = httpx.post(
        f"{VIDEO_SERVICE}/videos",
        json={
            "title": "AI Agents Deep Dive",
            "creator_id": user_id,
            "tags": ["ai"],
            "duration_seconds": 120,
        },
        timeout=5.0,
    )
    assert video_resp.status_code == 201

    feed_resp = httpx.get(f"{FEED_SERVICE}/feed/{user_id}", timeout=5.0)
    assert feed_resp.status_code == 200
    feed = feed_resp.json()
    assert feed["user_id"] == user_id
    assert "items" in feed
    assert len(feed["items"]) > 0
    first_item = feed["items"][0]
    assert "video_id" in first_item
    assert "score" in first_item
    assert "reason" in first_item


def test_event_idempotency():
    """Submitting the same idempotency_key twice returns duplicate_ignored on second call."""
    idempotency_key = f"integ-idem-{uuid.uuid4()}"
    payload = {
        "user_id": str(uuid.uuid4()),
        "video_id": str(uuid.uuid4()),
        "event_type": "like",
        "completion_rate": 0.9,
        "watch_time_seconds": 30,
        "idempotency_key": idempotency_key,
    }

    first = httpx.post(f"{EVENT_SERVICE}/events", json=payload, timeout=5.0)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "created"

    second = httpx.post(f"{EVENT_SERVICE}/events", json=payload, timeout=5.0)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "duplicate_ignored"
