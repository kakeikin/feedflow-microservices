# FeedFlow Microservices Phase 3 — Cache-Aware Ranking and Feed Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade Ranking Service from a 3-factor to a 4-factor scoring formula that incorporates `completion_rate` and net engagement (likes − skips), then add Redis cache-aside to Feed Service so Phase 2 async feature updates visibly affect feed quality while keeping feed latency low.

**Architecture:** `ranking.py` gains `compute_engagement` and `compute_completion_quality`; `compute_final_score` is updated to weights 0.45/0.20/0.20/0.15. `routes.py` in ranking-service removes `compute_popularity` and wires the two new functions. Feed Service gains `cache.py` (module-level Redis client with fail-open semantics); `routes.py` checks the cache before upstream calls and stores ranked results on miss with a 5-minute TTL. Redis 7 is added to Docker Compose.

**Tech Stack:** Python 3.11, FastAPI, redis==5.2.1 (asyncio), Redis 7 Alpine, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-04-30-feedflow-microservices-phase3-6-roadmap.md`

**Working directory for all tasks:** `/Users/jiaxin/ClaudeProjects/feedflow-microservices/`

---

## File Map

**Ranking Service (modify):**
- `services/ranking-service/app/ranking.py` — replace `compute_popularity` + `compute_final_score(3)` with `compute_engagement`, `compute_completion_quality`, `compute_final_score(4)`
- `services/ranking-service/app/routes.py` — swap `max_likes`/`compute_popularity` for `max_net_engagement`/`compute_engagement`/`compute_completion_quality`
- `services/ranking-service/tests/test_ranking.py` — replace popularity tests; add engagement + completion tests; update final_score tests
- `services/ranking-service/tests/test_routes.py` — **new** route-level tests using monkeypatch

**Feed Service (modify):**
- `services/feed-service/requirements.txt` — add `redis==5.2.1`
- `services/feed-service/app/cache.py` — **new**: module-level `_redis`, `connect/disconnect/get_feed/set_feed` with fail-open
- `services/feed-service/app/main.py` — add lifespan for Redis connect/disconnect
- `services/feed-service/app/routes.py` — import `cache`, add cache-aside before upstream calls
- `services/feed-service/tests/test_cache.py` — **new**: unit tests for cache module
- `services/feed-service/tests/test_routes.py` — add three new tests: cache_hit, cache_miss, redis_unavailable

**Infrastructure (modify):**
- `infra/docker-compose.yml` — add `redis` service; add `REDIS_URL` to `feed-service`; add `redis: condition: service_healthy` dependency

**Integration tests (create):**
- `tests/integration/test_phase3_cache_ranking.py`

---

## Task 1: Ranking Service — 4-factor formula in ranking.py

**Files:**
- Modify: `services/ranking-service/tests/test_ranking.py`
- Modify: `services/ranking-service/app/ranking.py`

### Step 1.1 — Replace test_ranking.py

Overwrite `services/ranking-service/tests/test_ranking.py` with:

```python
from datetime import datetime, timezone, timedelta
import pytest


def test_interest_match_full_match():
    from app.ranking import compute_interest_match
    tags = ["ai", "backend"]
    interests = [{"tag": "ai", "score": 1.0}, {"tag": "backend", "score": 0.8}]
    score = compute_interest_match(tags, interests)
    assert abs(score - (1.0 + 0.8) / 2) < 0.001


def test_interest_match_partial():
    from app.ranking import compute_interest_match
    tags = ["ai", "sports"]
    interests = [{"tag": "ai", "score": 1.0}]
    score = compute_interest_match(tags, interests)
    assert abs(score - 0.5) < 0.001


def test_interest_match_no_interests():
    from app.ranking import compute_interest_match
    assert compute_interest_match(["ai"], []) == 0.0


def test_interest_match_no_tags():
    from app.ranking import compute_interest_match
    assert compute_interest_match([], [{"tag": "ai", "score": 1.0}]) == 0.0


def test_freshness_very_new_video():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    assert compute_freshness(created_at) > 0.99


def test_freshness_old_video():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(days=8)
    assert compute_freshness(created_at) == 0.0


def test_freshness_midpoint():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(hours=84)
    assert abs(compute_freshness(created_at) - 0.5) < 0.02


def test_engagement_net_positive():
    from app.ranking import compute_engagement
    assert abs(compute_engagement(likes=9, skips=1, max_net_engagement=10) - 0.8) < 0.001


def test_engagement_skips_exceed_likes():
    from app.ranking import compute_engagement
    assert compute_engagement(likes=1, skips=5, max_net_engagement=10) == 0.0


def test_engagement_zero_max():
    from app.ranking import compute_engagement
    assert compute_engagement(likes=0, skips=0, max_net_engagement=0) == 0.0


def test_engagement_at_max():
    from app.ranking import compute_engagement
    assert compute_engagement(likes=10, skips=0, max_net_engagement=10) == pytest.approx(1.0)


def test_completion_quality_passthrough():
    from app.ranking import compute_completion_quality
    assert compute_completion_quality(0.75) == pytest.approx(0.75)


def test_completion_quality_zero():
    from app.ranking import compute_completion_quality
    assert compute_completion_quality(0.0) == 0.0


def test_final_score_all_ones():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(1.0, 1.0, 1.0, 1.0) - 1.0) < 0.001


def test_final_score_interest_only():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(1.0, 0.0, 0.0, 0.0) - 0.45) < 0.001


def test_final_score_freshness_only():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(0.0, 1.0, 0.0, 0.0) - 0.20) < 0.001


def test_final_score_engagement_only():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(0.0, 0.0, 1.0, 0.0) - 0.20) < 0.001


def test_final_score_completion_only():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(0.0, 0.0, 0.0, 1.0) - 0.15) < 0.001
```

- [ ] **Step 1.2 — Run tests to verify they fail**

```bash
cd services/ranking-service && pytest tests/test_ranking.py -v
```

Expected: several tests FAIL — `compute_engagement`, `compute_completion_quality` not defined; `compute_final_score` called with wrong arity.

- [ ] **Step 1.3 — Replace ranking.py**

Overwrite `services/ranking-service/app/ranking.py` with:

```python
from datetime import datetime, timezone


def compute_interest_match(video_tags: list[str], user_interests: list[dict]) -> float:
    """0.0–1.0: weighted fraction of video tags matched by user interest scores."""
    if not video_tags or not user_interests:
        return 0.0
    interest_map = {i["tag"]: i["score"] for i in user_interests}
    matched = sum(interest_map.get(tag, 0.0) for tag in video_tags)
    return matched / len(video_tags)


def compute_freshness(created_at: datetime) -> float:
    """0.0–1.0: linear decay — 1.0 when brand new, 0.0 at 7 days (168h) old."""
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = (now - created_at).total_seconds() / 3600
    return max(0.0, 1.0 - age_hours / 168.0)


def compute_engagement(likes: int, skips: int, max_net_engagement: int) -> float:
    """0.0–1.0: (likes - skips) normalized to the max net engagement in the candidate set."""
    net = likes - skips
    if net <= 0 or max_net_engagement == 0:
        return 0.0
    return net / max_net_engagement


def compute_completion_quality(completion_rate: float) -> float:
    """0.0–1.0: video completion rate as reported by VideoStats."""
    return completion_rate


def compute_final_score(
    interest_match: float,
    freshness: float,
    engagement: float,
    completion_quality: float,
) -> float:
    """Weighted combination: 0.45 interest + 0.20 freshness + 0.20 engagement + 0.15 completion."""
    return round(
        0.45 * interest_match
        + 0.20 * freshness
        + 0.20 * engagement
        + 0.15 * completion_quality,
        4,
    )
```

- [ ] **Step 1.4 — Run tests to verify they pass**

```bash
cd services/ranking-service && pytest tests/test_ranking.py -v
```

Expected: all 19 tests PASS.

- [ ] **Step 1.5 — Commit**

```bash
git add services/ranking-service/app/ranking.py services/ranking-service/tests/test_ranking.py
git commit -m "feat(ranking-service): upgrade to 4-factor formula with engagement and completion quality"
```

---

## Task 2: Ranking Service — wire 4-factor formula in routes.py + new route tests

**Files:**
- Modify: `services/ranking-service/app/routes.py`
- Create: `services/ranking-service/tests/test_routes.py`

- [ ] **Step 2.1 — Write failing route tests**

Create `services/ranking-service/tests/test_routes.py`:

```python
import pytest
from starlette.testclient import TestClient
from app.main import app

USER_INTERESTS = [{"tag": "ai", "score": 0.8}]
VIDEO_BASE = {
    "id": "v1",
    "title": "AI Video",
    "tags": ["ai"],
    "duration_seconds": 90,
    "created_at": "2026-04-30T00:00:00+00:00",
    "stats": {"views": 10, "likes": 5, "skips": 1, "completion_rate": 0.75},
}


def test_rank_returns_scored_items(monkeypatch):
    """Route returns ranked items with a non-zero score using the 4-factor formula."""
    async def mock_interests(user_id):
        return USER_INTERESTS

    async def mock_video(video_id):
        return VIDEO_BASE

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)
    monkeypatch.setattr("app.routes.clients.get_video", mock_video)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1"]})

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["video_id"] == "v1"
    assert items[0]["score"] > 0.0


def test_rank_higher_completion_rate_scores_higher(monkeypatch):
    """Video with completion_rate=1.0 outranks identical video with completion_rate=0.0."""
    async def mock_interests(user_id):
        return USER_INTERESTS

    low = dict(VIDEO_BASE, id="v1", stats=dict(VIDEO_BASE["stats"], completion_rate=0.0))
    high = dict(VIDEO_BASE, id="v2", stats=dict(VIDEO_BASE["stats"], completion_rate=1.0))

    async def mock_video(video_id):
        return low if video_id == "v1" else high

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)
    monkeypatch.setattr("app.routes.clients.get_video", mock_video)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1", "v2"]})

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert items[0]["video_id"] == "v2"
    assert items[0]["score"] > items[1]["score"]


def test_rank_empty_candidates(monkeypatch):
    async def mock_interests(user_id):
        return USER_INTERESTS

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": []})

    assert resp.status_code == 200
    assert resp.json() == []


def test_rank_degrades_when_video_unavailable(monkeypatch):
    async def mock_interests(user_id):
        return USER_INTERESTS

    async def mock_video(video_id):
        return None

    monkeypatch.setattr("app.routes.clients.get_user_interests", mock_interests)
    monkeypatch.setattr("app.routes.clients.get_video", mock_video)

    with TestClient(app) as client:
        resp = client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1"]})

    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2.2 — Run tests to verify they fail**

```bash
cd services/ranking-service && pytest tests/test_routes.py -v
```

Expected: `test_rank_higher_completion_rate_scores_higher` FAILS because `routes.py` still calls the old 3-factor `compute_final_score`. Other tests may pass or fail depending on import errors.

- [ ] **Step 2.3 — Replace routes.py**

Overwrite `services/ranking-service/app/routes.py` with:

```python
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from . import clients
from .schemas import RankRequest, RankItem
from .ranking import (
    compute_interest_match,
    compute_freshness,
    compute_engagement,
    compute_completion_quality,
    compute_final_score,
)

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "ranking-service", "status": "ok"}


@router.post("/rank", response_model=list[RankItem])
async def rank_videos(body: RankRequest) -> list[RankItem]:
    user_interests = await clients.get_user_interests(body.user_id)

    videos = []
    for video_id in body.candidate_video_ids:
        video = await clients.get_video(video_id)
        if video is not None:
            videos.append(video)

    if not videos:
        return []

    max_net_engagement = max(
        max(0, v.get("stats", {}).get("likes", 0) - v.get("stats", {}).get("skips", 0))
        for v in videos
    )

    results = []
    for video in videos:
        stats = video.get("stats", {})
        tags = video.get("tags", [])
        created_at_str = video.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(timezone.utc) - timedelta(days=9)

        interest = compute_interest_match(tags, user_interests)
        freshness = compute_freshness(created_at)
        engagement = compute_engagement(
            stats.get("likes", 0),
            stats.get("skips", 0),
            max_net_engagement,
        )
        completion_quality = compute_completion_quality(stats.get("completion_rate", 0.0))
        score = compute_final_score(interest, freshness, engagement, completion_quality)

        matched_tags = [t for t in tags if any(i["tag"] == t for i in user_interests)]
        reason = (
            f"matched user interest tags: {', '.join(matched_tags)}"
            if matched_tags
            else "no interest match"
        )

        results.append(RankItem(video_id=video["id"], score=score, reason=reason))

    results.sort(key=lambda x: x.score, reverse=True)
    return results
```

- [ ] **Step 2.4 — Run all ranking-service tests**

```bash
cd services/ranking-service && pytest tests/ -v
```

Expected: all tests PASS (19 unit + 4 route = 23 total).

- [ ] **Step 2.5 — Commit**

```bash
git add services/ranking-service/app/routes.py services/ranking-service/tests/test_routes.py
git commit -m "feat(ranking-service): wire 4-factor scoring in rank route; add route tests"
```

---

## Task 3: Feed Service — Redis cache module

**Files:**
- Modify: `services/feed-service/requirements.txt`
- Create: `services/feed-service/app/cache.py`
- Create: `services/feed-service/tests/test_cache.py`

- [ ] **Step 3.1 — Write failing cache tests**

Create `services/feed-service/tests/test_cache.py`:

```python
import asyncio
import json
from unittest.mock import AsyncMock


def test_get_feed_returns_cached_data():
    from app import cache
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps([{"video_id": "v1", "score": 0.9, "reason": "ai"}])
    cache._redis = mock_redis

    result = asyncio.run(cache.get_feed("u1"))

    assert result == [{"video_id": "v1", "score": 0.9, "reason": "ai"}]
    mock_redis.get.assert_awaited_once_with("feed:user:u1")
    cache._redis = None


def test_get_feed_returns_none_on_cache_miss():
    from app import cache
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    cache._redis = mock_redis

    result = asyncio.run(cache.get_feed("u1"))

    assert result is None
    cache._redis = None


def test_get_feed_returns_none_when_redis_unavailable():
    from app import cache
    cache._redis = None

    result = asyncio.run(cache.get_feed("u1"))

    assert result is None


def test_set_feed_stores_with_ttl():
    from app import cache
    mock_redis = AsyncMock()
    cache._redis = mock_redis

    items = [{"video_id": "v1", "score": 0.9, "reason": "ai"}]
    asyncio.run(cache.set_feed("u1", items))

    mock_redis.setex.assert_awaited_once_with("feed:user:u1", 300, json.dumps(items))
    cache._redis = None


def test_set_feed_no_op_when_redis_unavailable():
    from app import cache
    cache._redis = None

    asyncio.run(cache.set_feed("u1", []))  # must not raise


def test_get_feed_swallows_redis_exception():
    from app import cache
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("connection lost")
    cache._redis = mock_redis

    result = asyncio.run(cache.get_feed("u1"))

    assert result is None
    cache._redis = None
```

- [ ] **Step 3.2 — Run tests to verify they fail**

```bash
cd services/feed-service && pytest tests/test_cache.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.cache'`.

- [ ] **Step 3.3 — Add redis to requirements.txt**

Edit `services/feed-service/requirements.txt`:

```
fastapi==0.115.5
uvicorn==0.32.1
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
redis==5.2.1
```

- [ ] **Step 3.4 — Install redis locally for tests**

```bash
cd services/feed-service && pip install redis==5.2.1
```

- [ ] **Step 3.5 — Create cache.py**

Create `services/feed-service/app/cache.py`:

```python
import os
import json
import logging
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
FEED_TTL = 300  # 5 minutes

_redis: aioredis.Redis | None = None


async def connect() -> None:
    global _redis
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)


async def disconnect() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


async def get_feed(user_id: str) -> list[dict] | None:
    if _redis is None:
        return None
    try:
        data = await _redis.get(f"feed:user:{user_id}")
        return json.loads(data) if data else None
    except Exception:
        logger.warning("Redis get failed for feed:user:%s", user_id)
        return None


async def set_feed(user_id: str, items: list[dict]) -> None:
    if _redis is None:
        return
    try:
        await _redis.setex(f"feed:user:{user_id}", FEED_TTL, json.dumps(items))
    except Exception:
        logger.warning("Redis set failed for feed:user:%s", user_id)
```

- [ ] **Step 3.6 — Run tests to verify they pass**

```bash
cd services/feed-service && pytest tests/test_cache.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 3.7 — Commit**

```bash
git add services/feed-service/requirements.txt services/feed-service/app/cache.py services/feed-service/tests/test_cache.py
git commit -m "feat(feed-service): add Redis cache module with fail-open semantics"
```

---

## Task 4: Feed Service — cache-aside in routes.py + lifespan in main.py

**Files:**
- Modify: `services/feed-service/app/routes.py`
- Modify: `services/feed-service/app/main.py`
- Modify: `services/feed-service/tests/test_routes.py`

- [ ] **Step 4.1 — Add cache tests to test_routes.py**

Append to `services/feed-service/tests/test_routes.py` (keep the two existing tests, add three new ones):

```python
CACHED_ITEMS = [{"video_id": "v1", "score": 0.91, "reason": "ai"}]


def test_feed_returns_cache_hit_when_cached(monkeypatch):
    """When cache.get_feed returns data, source is cache_hit and upstream is not called."""
    async def mock_get_feed(user_id):
        return CACHED_ITEMS

    monkeypatch.setattr("app.routes.cache.get_feed", mock_get_feed)

    with TestClient(app) as client:
        resp = client.get("/feed/user-123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "cache_hit"
    assert data["items"][0]["video_id"] == "v1"
    assert data["items"][0]["score"] == 0.91


def test_feed_calls_ranking_on_cache_miss(monkeypatch):
    """Cache miss triggers the normal trending → ranking flow."""
    async def mock_get_feed(user_id):
        return None

    async def mock_set_feed(user_id, items):
        pass

    async def mock_get_trending():
        return TRENDING

    async def mock_rank(user_id, video_ids):
        return RANKED

    monkeypatch.setattr("app.routes.cache.get_feed", mock_get_feed)
    monkeypatch.setattr("app.routes.cache.set_feed", mock_set_feed)
    monkeypatch.setattr("app.routes.clients.get_trending_videos", mock_get_trending)
    monkeypatch.setattr("app.routes.clients.rank_videos", mock_rank)

    with TestClient(app) as client:
        resp = client.get("/feed/user-123")

    assert resp.status_code == 200
    assert resp.json()["source"] == "personalized_ranking"


def test_feed_serves_when_redis_unavailable(monkeypatch):
    """Redis unavailable (get_feed returns None) → feed still served via ranking."""
    async def mock_get_feed(user_id):
        return None

    async def mock_set_feed(user_id, items):
        pass

    async def mock_get_trending():
        return TRENDING

    async def mock_rank(user_id, video_ids):
        return RANKED

    monkeypatch.setattr("app.routes.cache.get_feed", mock_get_feed)
    monkeypatch.setattr("app.routes.cache.set_feed", mock_set_feed)
    monkeypatch.setattr("app.routes.clients.get_trending_videos", mock_get_trending)
    monkeypatch.setattr("app.routes.clients.rank_videos", mock_rank)

    with TestClient(app) as client:
        resp = client.get("/feed/user-123")

    assert resp.status_code == 200
    assert resp.json()["source"] == "personalized_ranking"
```

- [ ] **Step 4.2 — Run new tests to verify they fail**

```bash
cd services/feed-service && pytest tests/test_routes.py::test_feed_returns_cache_hit_when_cached tests/test_routes.py::test_feed_calls_ranking_on_cache_miss tests/test_routes.py::test_feed_serves_when_redis_unavailable -v
```

Expected: FAIL — `app.routes` has no `cache` attribute.

- [ ] **Step 4.3 — Replace routes.py**

Overwrite `services/feed-service/app/routes.py` with:

```python
from fastapi import APIRouter, HTTPException
from . import clients, cache
from .schemas import FeedItem, FeedResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "feed-service", "status": "ok"}


@router.get("/feed/{user_id}", response_model=FeedResponse)
async def get_feed(user_id: str) -> FeedResponse:
    cached = await cache.get_feed(user_id)
    if cached is not None:
        items = [FeedItem(**item) for item in cached]
        return FeedResponse(user_id=user_id, source="cache_hit", items=items)

    try:
        trending = await clients.get_trending_videos()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Video service unavailable") from exc

    candidate_ids = [v["id"] for v in trending]

    try:
        ranked = await clients.rank_videos(user_id, candidate_ids)
        items = [
            FeedItem(video_id=r["video_id"], score=r["score"], reason=r["reason"])
            for r in ranked
        ]
        await cache.set_feed(user_id, [item.model_dump() for item in items])
        return FeedResponse(user_id=user_id, source="personalized_ranking", items=items)
    except Exception:
        items = [
            FeedItem(video_id=v["id"], score=0.0, reason="trending_fallback")
            for v in trending
        ]
        return FeedResponse(user_id=user_id, source="trending_fallback", items=items)
```

- [ ] **Step 4.4 — Replace main.py**

Overwrite `services/feed-service/app/main.py` with:

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .routes import router
from . import cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("REDIS_URL"):
        await cache.connect()
    yield
    if os.environ.get("REDIS_URL"):
        await cache.disconnect()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 4.5 — Run all feed-service tests**

```bash
cd services/feed-service && pytest tests/ -v
```

Expected: all 5 tests PASS (2 existing + 3 new).

- [ ] **Step 4.6 — Commit**

```bash
git add services/feed-service/app/routes.py services/feed-service/app/main.py services/feed-service/tests/test_routes.py
git commit -m "feat(feed-service): add cache-aside Redis logic with source=cache_hit; lifespan connect/disconnect"
```

---

## Task 5: Docker Compose — Redis service + feed-service env

**Files:**
- Modify: `infra/docker-compose.yml`

- [ ] **Step 5.1 — Add Redis and update feed-service**

In `infra/docker-compose.yml`, add the `redis` service under the `# ─── Message Broker` section (after rabbitmq), and update `feed-service`. The complete updated sections are:

Add this block after the `rabbitmq` service definition (before `# ─── Application Services`):

```yaml
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

Replace the existing `feed-service` block with:

```yaml
  feed-service:
    build:
      context: ../services/feed-service
    ports:
      - "8005:8005"
    environment:
      VIDEO_SERVICE_URL: http://video-service:8002
      RANKING_SERVICE_URL: http://ranking-service:8004
      REDIS_URL: redis://redis:6379
    depends_on:
      - video-service
      - ranking-service
      redis:
        condition: service_healthy
```

- [ ] **Step 5.2 — Validate compose file**

```bash
docker compose -f infra/docker-compose.yml config --quiet
```

Expected: exits 0 with no output.

- [ ] **Step 5.3 — Commit**

```bash
git add infra/docker-compose.yml
git commit -m "feat(infra): add Redis 7, wire REDIS_URL into feed-service"
```

---

## Task 6: Integration Tests — Cache and Ranking

**Files:**
- Create: `tests/integration/test_phase3_cache_ranking.py`

- [ ] **Step 6.1 — Write integration tests**

Create `tests/integration/test_phase3_cache_ranking.py`:

```python
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

    resp2 = httpx.get(f"{FEED_SERVICE}/feed/{user_id}", timeout=5.0)
    assert resp2.status_code == 200
    assert resp2.json()["source"] == "cache_hit"


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

    # Poll until Feature Worker has processed both events
    poll_until(lambda: _get_interest_score(user_id, "ai") is not None, timeout=5.0)
    poll_until(lambda: _get_video_stats(video_id)["views"] > 0, timeout=5.0)

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
```

- [ ] **Step 6.2 — Verify syntax**

```bash
python -m py_compile tests/integration/test_phase3_cache_ranking.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 6.3 — Rebuild and start the stack**

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

Wait ~30 seconds for all services and healthchecks to settle.

- [ ] **Step 6.4 — Run existing integration tests (regression check)**

```bash
pytest tests/integration/test_feed_flow.py tests/integration/test_service_health.py tests/integration/test_feature_pipeline.py -v
```

Expected: all 8 existing tests PASS.

- [ ] **Step 6.5 — Run Phase 3 integration tests**

```bash
pytest tests/integration/test_phase3_cache_ranking.py -v
```

Expected: both tests PASS.
- `test_feed_cache_hit_on_second_request`: second request returns `source=cache_hit`
- `test_events_improve_ranking_score`: score increases after events processed by Feature Worker

- [ ] **Step 6.6 — Commit**

```bash
git add tests/integration/test_phase3_cache_ranking.py
git commit -m "test(integration): add Phase 3 cache hit and ranking improvement tests"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task covering it |
|---|---|
| Redis in Docker Compose | Task 5 |
| Feed Service cache-aside (hit, miss, fallback) | Tasks 3, 4 |
| Feed Service serves when Redis unavailable | Task 3 (fail-open), Task 4 (route test) |
| Ranking upgraded to use completion_rate | Tasks 1, 2 |
| Ranking upgraded to use engagement (likes/skips) | Tasks 1, 2 |
| `source` field in feed response: `cache_hit` | Task 4 |
| Integration: cache hit on second request | Task 6 |
| Integration: events influence ranking | Task 6 |
| All Phase 1+2 integration tests still pass | Task 6, Step 6.4 |

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:**
- `compute_engagement(likes, skips, max_net_engagement)` — used consistently in `ranking.py` and `routes.py`.
- `compute_final_score(interest_match, freshness, engagement, completion_quality)` — 4-arg signature used everywhere, including all updated tests.
- `cache.get_feed(user_id)` → `list[dict] | None` — used in routes.py and mocked correctly in test_routes.py.
- `cache.set_feed(user_id, items)` where `items = [item.model_dump() for item in items]` — `FeedItem.model_dump()` returns `{"video_id": ..., "score": ..., "reason": ...}`, matches `FeedItem(**item)` reconstruction on cache hit.
