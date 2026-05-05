# FeedFlow Microservices Phase 4 — Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Prometheus metrics and a Grafana dashboard to all 6 FeedFlow services, giving production-style observability over request rates, latency, cache behavior, event publishing, and worker reliability.

**Architecture:** Each of the 5 FastAPI services gets a `metrics.py` module, a `MetricsMiddleware`, and a `/metrics` endpoint (mounted via `make_asgi_app()`). The Feature Worker exposes metrics on port 9100 via `start_http_server`. Prometheus scrapes all 6 targets every 15 seconds; Grafana auto-provisions a data source and an 11-panel dashboard from committed JSON files.

**Tech Stack:** `prometheus-client==0.20.0`, Starlette `BaseHTTPMiddleware`, `prom/prometheus:v2.51.0`, `grafana/grafana:10.4.0`, Docker Compose volumes for config files.

---

## File Map

**New files:**
- `services/feed-service/app/metrics.py`
- `services/feed-service/tests/test_metrics.py`
- `services/ranking-service/app/metrics.py`
- `services/ranking-service/tests/test_metrics.py`
- `services/event-service/app/metrics.py`
- `services/event-service/tests/test_metrics.py`
- `services/user-service/app/metrics.py`
- `services/user-service/tests/test_metrics.py`
- `services/video-service/app/metrics.py`
- `services/video-service/tests/test_metrics.py`
- `services/feature-worker/app/metrics.py`
- `services/feature-worker/tests/test_metrics.py`
- `infra/prometheus/prometheus.yml`
- `infra/grafana/provisioning/datasources/datasource.yml`
- `infra/grafana/provisioning/dashboards/dashboard.yml`
- `infra/grafana/dashboards/feedflow.json`

**Modified files:**
- `services/feed-service/requirements.txt` — add prometheus-client
- `services/feed-service/app/main.py` — add MetricsMiddleware + mount /metrics
- `services/feed-service/app/routes.py` — increment cache hit/miss/fallback counters
- `services/ranking-service/requirements.txt` — add prometheus-client
- `services/ranking-service/app/main.py` — add MetricsMiddleware + mount /metrics
- `services/ranking-service/app/routes.py` — observe candidate_count, increment upstream_error
- `services/event-service/requirements.txt` — add prometheus-client
- `services/event-service/app/main.py` — add MetricsMiddleware + mount /metrics
- `services/event-service/app/routes.py` — add ingest/duplicate/publish counters, extract publish function
- `services/user-service/requirements.txt` — add prometheus-client
- `services/user-service/app/main.py` — add MetricsMiddleware + mount /metrics
- `services/video-service/requirements.txt` — add prometheus-client
- `services/video-service/app/main.py` — add MetricsMiddleware + mount /metrics
- `services/feature-worker/requirements.txt` — add prometheus-client
- `services/feature-worker/app/consumer.py` — increment all worker metrics
- `services/feature-worker/app/main.py` — add start_metrics_server()
- `infra/docker-compose.yml` — add prometheus + grafana services, expose 9100 on feature-worker

---

## Task 1: Add prometheus-client to all services

**Files:**
- Modify: `services/feed-service/requirements.txt`
- Modify: `services/ranking-service/requirements.txt`
- Modify: `services/event-service/requirements.txt`
- Modify: `services/user-service/requirements.txt`
- Modify: `services/video-service/requirements.txt`
- Modify: `services/feature-worker/requirements.txt`

- [ ] **Step 1: Add prometheus-client to feed-service**

The full content of `services/feed-service/requirements.txt` after the change:

```
fastapi==0.115.5
uvicorn==0.32.1
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
redis==5.2.1
prometheus-client==0.20.0
```

- [ ] **Step 2: Add prometheus-client to ranking-service**

The full content of `services/ranking-service/requirements.txt` after the change:

```
fastapi==0.115.5
uvicorn==0.32.1
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
prometheus-client==0.20.0
```

- [ ] **Step 3: Add prometheus-client to event-service**

The full content of `services/event-service/requirements.txt` after the change:

```
fastapi==0.115.5
uvicorn==0.32.1
sqlalchemy==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
aio-pika==9.4.3
prometheus-client==0.20.0
```

- [ ] **Step 4: Add prometheus-client to user-service**

The full content of `services/user-service/requirements.txt` after the change:

```
fastapi==0.115.5
uvicorn==0.32.1
sqlalchemy==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
prometheus-client==0.20.0
```

- [ ] **Step 5: Add prometheus-client to video-service**

The full content of `services/video-service/requirements.txt` after the change:

```
fastapi==0.115.5
uvicorn==0.32.1
sqlalchemy==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
prometheus-client==0.20.0
```

- [ ] **Step 6: Add prometheus-client to feature-worker**

The full content of `services/feature-worker/requirements.txt` after the change:

```
aio-pika==9.4.3
httpx==0.28.1
pytest==8.3.4
prometheus-client==0.20.0
```

- [ ] **Step 7: Commit**

```bash
git add services/feed-service/requirements.txt \
        services/ranking-service/requirements.txt \
        services/event-service/requirements.txt \
        services/user-service/requirements.txt \
        services/video-service/requirements.txt \
        services/feature-worker/requirements.txt
git commit -m "feat: add prometheus-client to all service requirements"
```

---

## Task 2: feed-service — metrics, middleware, business counters, tests

**Files:**
- Create: `services/feed-service/app/metrics.py`
- Modify: `services/feed-service/app/main.py`
- Modify: `services/feed-service/app/routes.py`
- Create: `services/feed-service/tests/test_metrics.py`

### Background

`feed-service` has these routes: `GET /health`, `GET /feed/{user_id}`. The cache-aside logic in `routes.py` already has explicit hit/miss/fallback branches — each needs a counter increment. The `/metrics` endpoint is a Prometheus ASGI sub-app mounted at `/metrics`; the middleware skips it.

**Four MetricsMiddleware guardrails (apply identically to all 5 FastAPI services):**
1. Skip `/metrics` and `/metrics/` via `startswith("/metrics")`
2. Record metrics even on exceptions — use `try/finally`, default `status_code = 500`
3. Use route template label (`scope["route"].path`) not raw URL — read `scope["route"]` inside `finally` (after `call_next`) so routing is fully resolved
4. Status code label is `str(status_code)`

- [ ] **Step 1: Write failing tests for feed-service metrics**

Create `services/feed-service/tests/test_metrics.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/feed-service && pytest tests/test_metrics.py -v
```

Expected: all 7 tests FAIL with `ImportError` or `ModuleNotFoundError` since `metrics.py` doesn't exist yet.

- [ ] **Step 3: Create `services/feed-service/app/metrics.py`**

```python
from prometheus_client import Counter, Histogram

FEED_REQUEST_TOTAL = Counter(
    "feed_request_total",
    "Total feed service requests",
    ["method", "route", "status"],
)
FEED_REQUEST_LATENCY = Histogram(
    "feed_request_latency_seconds",
    "Feed service request latency in seconds",
    ["method", "route"],
)
FEED_CACHE_HIT_TOTAL = Counter("feed_cache_hit_total", "Feed cache hits")
FEED_CACHE_MISS_TOTAL = Counter("feed_cache_miss_total", "Feed cache misses")
FEED_FALLBACK_TOTAL = Counter("feed_fallback_total", "Feed fallback to trending (ranking failed)")
```

- [ ] **Step 4: Rewrite `services/feed-service/app/main.py`**

```python
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import make_asgi_app
from .routes import router
from . import cache
from .metrics import FEED_REQUEST_TOTAL, FEED_REQUEST_LATENCY


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/metrics"):
            return await call_next(request)

        start = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            FEED_REQUEST_TOTAL.labels(request.method, path, str(status_code)).inc()
            FEED_REQUEST_LATENCY.labels(request.method, path).observe(time.time() - start)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("REDIS_URL"):
        await cache.connect()
    try:
        yield
    finally:
        if os.environ.get("REDIS_URL"):
            await cache.disconnect()


app = FastAPI(lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
app.include_router(router)
app.mount("/metrics", make_asgi_app())
```

- [ ] **Step 5: Modify `services/feed-service/app/routes.py` to increment business counters**

Add the import at the top and three counter increments in the route handler. Full file content:

```python
import logging
from fastapi import APIRouter, HTTPException
from . import clients, cache
from .schemas import FeedItem, FeedResponse
from .metrics import FEED_CACHE_HIT_TOTAL, FEED_CACHE_MISS_TOTAL, FEED_FALLBACK_TOTAL

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "feed-service", "status": "ok"}


@router.get("/feed/{user_id}", response_model=FeedResponse)
async def get_feed(user_id: str) -> FeedResponse:
    cached = await cache.get_feed(user_id)
    if cached is not None:
        FEED_CACHE_HIT_TOTAL.inc()
        items = [FeedItem(**item) for item in cached]
        return FeedResponse(user_id=user_id, source="cache_hit", items=items)

    FEED_CACHE_MISS_TOTAL.inc()

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
    except Exception as exc:
        logger.warning("Ranking failed for user %s, falling back to trending: %s", user_id, exc)
        FEED_FALLBACK_TOTAL.inc()
        items = [
            FeedItem(video_id=v["id"], score=0.0, reason="trending_fallback")
            for v in trending
        ]
        return FeedResponse(user_id=user_id, source="trending_fallback", items=items)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd services/feed-service && pytest tests/test_metrics.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 7: Verify existing tests still pass**

```bash
cd services/feed-service && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add services/feed-service/app/metrics.py \
        services/feed-service/app/main.py \
        services/feed-service/app/routes.py \
        services/feed-service/tests/test_metrics.py
git commit -m "feat(feed-service): add Prometheus metrics middleware and business counters"
```

---

## Task 3: ranking-service — metrics, middleware, business counters, tests

**Files:**
- Create: `services/ranking-service/app/metrics.py`
- Modify: `services/ranking-service/app/main.py`
- Modify: `services/ranking-service/app/routes.py`
- Create: `services/ranking-service/tests/test_metrics.py`

### Background

`ranking-service` has routes `GET /health` and `POST /rank`. In `routes.py`, after the video list is resolved we observe `ranking_candidate_count`. When `get_video` returns `None` (any HTTP error; see `clients.py` which swallows all `httpx.HTTPError` and returns `None`), we increment `ranking_upstream_error_total`. The `ranking_candidate_count` histogram uses custom buckets matching expected feed sizes.

- [ ] **Step 1: Write failing tests for ranking-service metrics**

Create `services/ranking-service/tests/test_metrics.py`:

```python
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("ranking_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("ranking_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_latency_histogram_count_increments():
    with TestClient(app) as client:
        before = _counter("ranking_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
        client.get("/health")
        after = _counter("ranking_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    val = _counter("ranking_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    with TestClient(app) as client:
        client.get("/health")
    template = _counter("ranking_request_total", {"method": "GET", "route": "/health", "status": "200"})
    # /health has no path param — verify the POST /rank template works
    with patch("app.routes.clients.get_user_interests", new_callable=AsyncMock, return_value=[]), \
         patch("app.routes.clients.get_video", new_callable=AsyncMock, return_value=None):
        with TestClient(app) as client:
            client.post("/rank", json={"user_id": "u1", "candidate_video_ids": []})
    rank_val = _counter("ranking_request_total", {"method": "POST", "route": "/rank", "status": "200"})
    assert rank_val is not None


def test_candidate_count_histogram_observes_resolved_count():
    video = {
        "id": "v1", "tags": ["tech"], "created_at": "2026-04-01T00:00:00Z",
        "stats": {"likes": 5, "skips": 0, "completion_rate": 0.8},
    }
    with patch("app.routes.clients.get_user_interests", new_callable=AsyncMock, return_value=[{"tag": "tech", "score": 0.9}]), \
         patch("app.routes.clients.get_video", new_callable=AsyncMock, return_value=video):
        with TestClient(app) as client:
            before = _counter("ranking_candidate_count_count") or 0.0
            client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v1"]})
            after = _counter("ranking_candidate_count_count") or 0.0
    assert after - before == 1.0


def test_upstream_error_counter_increments_when_video_returns_none():
    with patch("app.routes.clients.get_user_interests", new_callable=AsyncMock, return_value=[]), \
         patch("app.routes.clients.get_video", new_callable=AsyncMock, return_value=None):
        with TestClient(app) as client:
            before = _counter("ranking_upstream_error_total") or 0.0
            client.post("/rank", json={"user_id": "u1", "candidate_video_ids": ["v-missing"]})
            after = _counter("ranking_upstream_error_total") or 0.0
    assert after - before == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/ranking-service && pytest tests/test_metrics.py -v
```

Expected: all 6 tests FAIL.

- [ ] **Step 3: Create `services/ranking-service/app/metrics.py`**

```python
from prometheus_client import Counter, Histogram

RANKING_REQUEST_TOTAL = Counter(
    "ranking_request_total",
    "Total ranking service requests",
    ["method", "route", "status"],
)
RANKING_REQUEST_LATENCY = Histogram(
    "ranking_request_latency_seconds",
    "Ranking service request latency in seconds",
    ["method", "route"],
)
RANKING_CANDIDATE_COUNT = Histogram(
    "ranking_candidate_count",
    "Number of candidate videos resolved for ranking",
    buckets=[1, 5, 10, 20, 50, 100, 200],
)
RANKING_UPSTREAM_ERROR_TOTAL = Counter(
    "ranking_upstream_error_total",
    "Total upstream fetch failures (video or user service)",
)
```

- [ ] **Step 4: Rewrite `services/ranking-service/app/main.py`**

```python
import time
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import make_asgi_app
from .routes import router
from .metrics import RANKING_REQUEST_TOTAL, RANKING_REQUEST_LATENCY


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/metrics"):
            return await call_next(request)

        start = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            RANKING_REQUEST_TOTAL.labels(request.method, path, str(status_code)).inc()
            RANKING_REQUEST_LATENCY.labels(request.method, path).observe(time.time() - start)


app = FastAPI()
app.add_middleware(MetricsMiddleware)
app.include_router(router)
app.mount("/metrics", make_asgi_app())
```

- [ ] **Step 5: Modify `services/ranking-service/app/routes.py` to add candidate count + upstream error**

Full file content after modifications:

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
from .metrics import RANKING_CANDIDATE_COUNT, RANKING_UPSTREAM_ERROR_TOTAL

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
        else:
            RANKING_UPSTREAM_ERROR_TOTAL.inc()

    RANKING_CANDIDATE_COUNT.observe(len(videos))

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
            created_at = datetime.now(timezone.utc) - timedelta(days=9)  # beyond 7-day decay window → freshness=0.0

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

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd services/ranking-service && pytest tests/test_metrics.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 7: Verify existing tests still pass**

```bash
cd services/ranking-service && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add services/ranking-service/app/metrics.py \
        services/ranking-service/app/main.py \
        services/ranking-service/app/routes.py \
        services/ranking-service/tests/test_metrics.py
git commit -m "feat(ranking-service): add Prometheus metrics middleware and business counters"
```

---

## Task 4: event-service — metrics, middleware, extract publish function, business counters, tests

**Files:**
- Create: `services/event-service/app/metrics.py`
- Modify: `services/event-service/app/main.py`
- Modify: `services/event-service/app/routes.py`
- Create: `services/event-service/tests/test_metrics.py`

### Background

`event-service` routes: `GET /health`, `POST /events`, `GET /events`. The publish metrics can't be tested via `TestClient` because `publisher.publish_event` runs in a `BackgroundTask` that completes after the response returns. Fix: extract a standalone async function `_publish_and_record(event_data)` that wraps the publisher call and increments success/failure. The `BackgroundTask` calls `_publish_and_record`; tests call it directly.

Counters:
- `event_ingest_total` — incremented after successful DB commit (new event created)
- `event_duplicate_total` — incremented in the IntegrityError handler (idempotency key already seen)
- `event_publish_success_total` — incremented inside `_publish_and_record` on success
- `event_publish_failure_total` — incremented inside `_publish_and_record` on exception

- [ ] **Step 1: Write failing tests for event-service metrics**

Create `services/event-service/tests/test_metrics.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from prometheus_client import REGISTRY

from app.main import app
from app.database import get_db
from app.routes import _publish_and_record


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def _committed_db():
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _duplicate_db():
    db = MagicMock()
    exc = IntegrityError(None, None, Exception("duplicate"))
    exc.orig = MagicMock()
    exc.orig.pgcode = "23505"
    db.commit = AsyncMock(side_effect=exc)
    db.rollback = AsyncMock()
    return db


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("event_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("event_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    val = _counter("event_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    db = _committed_db()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock):
        with TestClient(app) as client:
            client.post("/events", json={
                "user_id": "u1", "video_id": "v1", "event_type": "like", "idempotency_key": "k1",
            })
    app.dependency_overrides.clear()
    template = _counter("event_request_total", {"method": "POST", "route": "/events", "status": "201"})
    raw = _counter("event_request_total", {"method": "POST", "route": "/events/something", "status": "201"})
    assert template is not None
    assert raw is None


def test_ingest_counter_increments_on_new_event():
    db = _committed_db()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock):
        with TestClient(app) as client:
            before = _counter("event_ingest_total") or 0.0
            client.post("/events", json={
                "user_id": "u1", "video_id": "v1", "event_type": "like", "idempotency_key": "k2",
            })
            after = _counter("event_ingest_total") or 0.0
    app.dependency_overrides.clear()
    assert after - before == 1.0


def test_duplicate_counter_increments_on_duplicate_event():
    db = _duplicate_db()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        before = _counter("event_duplicate_total") or 0.0
        client.post("/events", json={
            "user_id": "u1", "video_id": "v1", "event_type": "like", "idempotency_key": "k-dup",
        })
        after = _counter("event_duplicate_total") or 0.0
    app.dependency_overrides.clear()
    assert after - before == 1.0


def test_publish_success_counter_increments_when_publish_succeeds():
    event_data = {"event_id": "e1", "user_id": "u1", "video_id": "v1", "event_type": "like"}
    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock):
        before = _counter("event_publish_success_total") or 0.0
        asyncio.get_event_loop().run_until_complete(_publish_and_record(event_data))
        after = _counter("event_publish_success_total") or 0.0
    assert after - before == 1.0


def test_publish_failure_counter_increments_when_publish_fails():
    event_data = {"event_id": "e1", "user_id": "u1", "video_id": "v1", "event_type": "like"}
    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock, side_effect=Exception("broker down")):
        before = _counter("event_publish_failure_total") or 0.0
        asyncio.get_event_loop().run_until_complete(_publish_and_record(event_data))
        after = _counter("event_publish_failure_total") or 0.0
    assert after - before == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/event-service && pytest tests/test_metrics.py -v
```

Expected: all 7 tests FAIL.

- [ ] **Step 3: Create `services/event-service/app/metrics.py`**

```python
from prometheus_client import Counter, Histogram

EVENT_REQUEST_TOTAL = Counter(
    "event_request_total",
    "Total event service requests",
    ["method", "route", "status"],
)
EVENT_REQUEST_LATENCY = Histogram(
    "event_request_latency_seconds",
    "Event service request latency in seconds",
    ["method", "route"],
)
EVENT_INGEST_TOTAL = Counter("event_ingest_total", "Total new events successfully ingested")
EVENT_DUPLICATE_TOTAL = Counter("event_duplicate_total", "Total duplicate events rejected by idempotency key")
EVENT_PUBLISH_SUCCESS_TOTAL = Counter("event_publish_success_total", "Total events successfully published to RabbitMQ")
EVENT_PUBLISH_FAILURE_TOTAL = Counter("event_publish_failure_total", "Total event publish failures")
```

- [ ] **Step 4: Rewrite `services/event-service/app/main.py`**

```python
import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import make_asgi_app
from .database import engine, Base
from .routes import router
from . import publisher
from .metrics import EVENT_REQUEST_TOTAL, EVENT_REQUEST_LATENCY


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/metrics"):
            return await call_next(request)

        start = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            EVENT_REQUEST_TOTAL.labels(request.method, path, str(status_code)).inc()
            EVENT_REQUEST_LATENCY.labels(request.method, path).observe(time.time() - start)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if os.environ.get("RABBITMQ_URL"):
        await publisher.connect()
    yield
    if os.environ.get("RABBITMQ_URL"):
        await publisher.disconnect()


app = FastAPI(title="Event Service", lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
app.include_router(router)
app.mount("/metrics", make_asgi_app())
```

- [ ] **Step 5: Modify `services/event-service/app/routes.py` to add counters and extract publish function**

Full file content:

```python
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database import get_db
from .models import Event
from .schemas import EventCreate, EventResponse
from . import publisher
from .metrics import (
    EVENT_INGEST_TOTAL,
    EVENT_DUPLICATE_TOTAL,
    EVENT_PUBLISH_SUCCESS_TOTAL,
    EVENT_PUBLISH_FAILURE_TOTAL,
)

router = APIRouter()


async def _publish_and_record(event_data: dict) -> None:
    try:
        await publisher.publish_event(event_data)
        EVENT_PUBLISH_SUCCESS_TOTAL.inc()
    except Exception:
        EVENT_PUBLISH_FAILURE_TOTAL.inc()


@router.get("/health")
async def health():
    return {"service": "event-service", "status": "ok"}


@router.post("/events")
async def create_event(
    body: EventCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    event = Event(
        id=str(uuid.uuid4()),
        user_id=body.user_id,
        video_id=body.video_id,
        event_type=body.event_type,
        completion_rate=body.completion_rate,
        watch_time_seconds=body.watch_time_seconds,
        idempotency_key=body.idempotency_key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    try:
        await db.commit()
        event_data = {
            "event_id": event.id,
            "user_id": event.user_id,
            "video_id": event.video_id,
            "event_type": event.event_type,
            "completion_rate": event.completion_rate,
            "watch_time_seconds": event.watch_time_seconds,
        }
        EVENT_INGEST_TOTAL.inc()
        background_tasks.add_task(_publish_and_record, event_data)
        return JSONResponse(status_code=201, content={"id": event.id, "status": "created"})
    except IntegrityError as exc:
        await db.rollback()
        pg_code = getattr(exc.orig, "pgcode", None)
        if pg_code == "23505":
            EVENT_DUPLICATE_TOTAL.inc()
            return JSONResponse(status_code=200, content={"status": "duplicate_ignored"})
        raise


@router.get("/events", response_model=list[EventResponse])
async def list_events(user_id: str | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Event)
    if user_id:
        query = query.where(Event.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd services/event-service && pytest tests/test_metrics.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 7: Verify existing tests still pass**

The existing `test_routes_publisher.py` tests use `publisher.publish_event` directly via mock. The refactored code wraps it in `_publish_and_record` which the BackgroundTask calls — the existing test mocks `app.routes.publisher.publish_event` which still works because `_publish_and_record` calls it.

```bash
cd services/event-service && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add services/event-service/app/metrics.py \
        services/event-service/app/main.py \
        services/event-service/app/routes.py \
        services/event-service/tests/test_metrics.py
git commit -m "feat(event-service): add Prometheus metrics middleware and business counters"
```

---

## Task 5: user-service — metrics, middleware, tests

**Files:**
- Create: `services/user-service/app/metrics.py`
- Modify: `services/user-service/app/main.py`
- Create: `services/user-service/tests/test_metrics.py`

### Background

`user-service` routes: `GET /health`, `POST /users`, `GET /users/{user_id}`, `GET /users/{user_id}/interests`, `POST /users/{user_id}/interests`, `PATCH /users/{user_id}/interests/{tag}`. No new business counters — only the per-request counter and latency histogram. The route template test verifies `GET /users/{user_id}` is labeled correctly (not with the actual user ID).

- [ ] **Step 1: Write failing tests for user-service metrics**

Create `services/user-service/tests/test_metrics.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app
from app.database import get_db


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("user_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("user_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_latency_histogram_count_increments():
    with TestClient(app) as client:
        before = _counter("user_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
        client.get("/health")
        after = _counter("user_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    val = _counter("user_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    # Mock DB to return a user for GET /users/{user_id}
    user_mock = MagicMock()
    user_mock.id = "u-123"
    user_mock.email = "test@test.com"
    user_mock.display_name = "Test"
    user_mock.created_at = MagicMock()
    user_mock.created_at.isoformat.return_value = "2026-01-01T00:00:00"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = user_mock

    db = MagicMock()
    db.execute = AsyncMock(return_value=result_mock)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        client.get("/users/u-123")
    app.dependency_overrides.clear()

    template = _counter("user_request_total", {"method": "GET", "route": "/users/{user_id}", "status": "200"})
    raw = _counter("user_request_total", {"method": "GET", "route": "/users/u-123", "status": "200"})
    assert template is not None
    assert raw is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/user-service && pytest tests/test_metrics.py -v
```

Expected: all 4 tests FAIL.

- [ ] **Step 3: Create `services/user-service/app/metrics.py`**

```python
from prometheus_client import Counter, Histogram

USER_REQUEST_TOTAL = Counter(
    "user_request_total",
    "Total user service requests",
    ["method", "route", "status"],
)
USER_REQUEST_LATENCY = Histogram(
    "user_request_latency_seconds",
    "User service request latency in seconds",
    ["method", "route"],
)
```

- [ ] **Step 4: Rewrite `services/user-service/app/main.py`**

```python
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import make_asgi_app
from .database import engine, Base
from .routes import router
from .metrics import USER_REQUEST_TOTAL, USER_REQUEST_LATENCY


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/metrics"):
            return await call_next(request)

        start = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            USER_REQUEST_TOTAL.labels(request.method, path, str(status_code)).inc()
            USER_REQUEST_LATENCY.labels(request.method, path).observe(time.time() - start)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
app.include_router(router)
app.mount("/metrics", make_asgi_app())
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd services/user-service && pytest tests/test_metrics.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Verify existing tests still pass**

```bash
cd services/user-service && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add services/user-service/app/metrics.py \
        services/user-service/app/main.py \
        services/user-service/tests/test_metrics.py
git commit -m "feat(user-service): add Prometheus metrics middleware"
```

---

## Task 6: video-service — metrics, middleware, tests

**Files:**
- Create: `services/video-service/app/metrics.py`
- Modify: `services/video-service/app/main.py`
- Create: `services/video-service/tests/test_metrics.py`

### Background

`video-service` routes: `GET /health`, `POST /videos`, `GET /videos`, `GET /videos/trending`, `GET /videos/{video_id}`, `PATCH /videos/{video_id}/stats`. No new business counters. The route template test verifies `GET /videos/{video_id}` label (not raw `/videos/v-123`).

- [ ] **Step 1: Write failing tests for video-service metrics**

Create `services/video-service/tests/test_metrics.py`:

```python
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app
from app.database import get_db


def _counter(name, labels=None):
    return REGISTRY.get_sample_value(name, labels or {})


def test_request_total_increments_on_health():
    with TestClient(app) as client:
        before = _counter("video_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
        client.get("/health")
        after = _counter("video_request_total", {"method": "GET", "route": "/health", "status": "200"}) or 0.0
    assert after - before == 1.0


def test_latency_histogram_count_increments():
    with TestClient(app) as client:
        before = _counter("video_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
        client.get("/health")
        after = _counter("video_request_latency_seconds_count", {"method": "GET", "route": "/health"}) or 0.0
    assert after - before == 1.0


def test_metrics_endpoint_not_counted_in_request_total():
    with TestClient(app) as client:
        client.get("/metrics")
    val = _counter("video_request_total", {"method": "GET", "route": "/metrics", "status": "200"})
    assert val is None


def test_route_label_uses_template_not_raw_path():
    # Mock DB to return a video for GET /videos/{video_id}
    stats_mock = MagicMock()
    stats_mock.views = 0
    stats_mock.likes = 0
    stats_mock.skips = 0
    stats_mock.completion_rate = 0.0

    video_mock = MagicMock()
    video_mock.id = "v-123"
    video_mock.title = "Test"
    video_mock.creator_id = "c1"
    video_mock.tags = []
    video_mock.duration_seconds = 60
    video_mock.created_at = MagicMock()
    video_mock.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    video_mock.stats = stats_mock

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = video_mock

    db = MagicMock()
    db.execute = AsyncMock(return_value=result_mock)

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        client.get("/videos/v-123")
    app.dependency_overrides.clear()

    template = _counter("video_request_total", {"method": "GET", "route": "/videos/{video_id}", "status": "200"})
    raw = _counter("video_request_total", {"method": "GET", "route": "/videos/v-123", "status": "200"})
    assert template is not None
    assert raw is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/video-service && pytest tests/test_metrics.py -v
```

Expected: all 4 tests FAIL.

- [ ] **Step 3: Create `services/video-service/app/metrics.py`**

```python
from prometheus_client import Counter, Histogram

VIDEO_REQUEST_TOTAL = Counter(
    "video_request_total",
    "Total video service requests",
    ["method", "route", "status"],
)
VIDEO_REQUEST_LATENCY = Histogram(
    "video_request_latency_seconds",
    "Video service request latency in seconds",
    ["method", "route"],
)
```

- [ ] **Step 4: Rewrite `services/video-service/app/main.py`**

```python
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import make_asgi_app
from .database import engine, Base
from .routes import router
from .metrics import VIDEO_REQUEST_TOTAL, VIDEO_REQUEST_LATENCY


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/metrics"):
            return await call_next(request)

        start = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            VIDEO_REQUEST_TOTAL.labels(request.method, path, str(status_code)).inc()
            VIDEO_REQUEST_LATENCY.labels(request.method, path).observe(time.time() - start)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(MetricsMiddleware)
app.include_router(router)
app.mount("/metrics", make_asgi_app())
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd services/video-service && pytest tests/test_metrics.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Verify existing tests still pass**

```bash
cd services/video-service && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add services/video-service/app/metrics.py \
        services/video-service/app/main.py \
        services/video-service/tests/test_metrics.py
git commit -m "feat(video-service): add Prometheus metrics middleware"
```

---

## Task 7: feature-worker — metrics, consumer instrumentation, metrics server, tests

**Files:**
- Create: `services/feature-worker/app/metrics.py`
- Modify: `services/feature-worker/app/consumer.py`
- Modify: `services/feature-worker/app/main.py`
- Create: `services/feature-worker/tests/test_metrics.py`

### Background

Feature Worker has no FastAPI app. It exposes metrics via `prometheus_client.start_http_server(9100)` which starts a background thread HTTP server. This is called only in the `__main__` block to avoid port conflicts in tests.

**Counter semantics (critical — must be exact):**
- `worker_message_processed_total` — increment only after `message.ack()` is called for a successfully processed message. Not for schema errors, unknown event types, or 4xx skips (those also ack but are not "processed").
- `worker_message_failed_total` — increment only for non-retryable terminal failures: after `message.ack()` is called in the DLQ path (max retries exhausted). Also increment for 4xx upstream errors that skip the message (schema errors and unknown event types are not failures, just skips — do not increment).
- `worker_retry_total` — increment each time a message is republished for retry (before max retries reached). A single message can contribute multiple increments.
- `worker_dlq_total` — increment when a message is routed to the DLQ (after max retries exhausted). One message contributes exactly one increment.

**Mutual exclusivity:** A message contributes to exactly one of: `processed_total` OR (`failed_total` + `dlq_total`). It may contribute to multiple `retry_total` increments before the final outcome.

**Latency histogram:** wraps total message processing time from receipt to ack/nack. Start timer at the top of `handle_message`, observe in a `finally` block before returning.

- [ ] **Step 1: Write failing tests for feature-worker metrics**

Create `services/feature-worker/tests/test_metrics.py`:

```python
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
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
    return asyncio.get_event_loop().run_until_complete(coro)


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
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=Exception("transient")):
        before = _counter("worker_message_processed_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_message_processed_total") or 0.0
    assert after - before == 0.0


def test_retry_total_increments_when_message_republished():
    msg = _make_message(VALID_BODY, retry_count=0)
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=Exception("transient")):
        before = _counter("worker_retry_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_retry_total") or 0.0
    assert after - before == 1.0


def test_dlq_total_increments_when_max_retries_exceeded():
    msg = _make_message(VALID_BODY, retry_count=3)  # MAX_RETRIES = 3
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=Exception("transient")):
        before = _counter("worker_dlq_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_dlq_total") or 0.0
    assert after - before == 1.0


def test_failed_total_increments_when_max_retries_exceeded():
    msg = _make_message(VALID_BODY, retry_count=3)  # MAX_RETRIES = 3
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=Exception("transient")):
        before = _counter("worker_message_failed_total") or 0.0
        run(handle_message(msg, exchange, default_exchange))
        after = _counter("worker_message_failed_total") or 0.0
    assert after - before == 1.0


def test_failed_total_does_not_increment_on_first_retry():
    msg = _make_message(VALID_BODY, retry_count=0)
    exchange, default_exchange = _make_exchanges()
    with patch("app.consumer.clients.get_video", new_callable=AsyncMock, side_effect=Exception("transient")):
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/feature-worker && pytest tests/test_metrics.py -v
```

Expected: all 7 tests FAIL.

- [ ] **Step 3: Create `services/feature-worker/app/metrics.py`**

```python
from prometheus_client import Counter, Histogram

WORKER_PROCESSED_TOTAL = Counter(
    "worker_message_processed_total",
    "Total messages successfully processed and ACKed",
)
WORKER_FAILED_TOTAL = Counter(
    "worker_message_failed_total",
    "Total messages that failed non-retryably (DLQ or 4xx skip after max retries)",
)
WORKER_RETRY_TOTAL = Counter(
    "worker_retry_total",
    "Total times a message was republished for retry",
)
WORKER_DLQ_TOTAL = Counter(
    "worker_dlq_total",
    "Total messages routed to the dead-letter queue",
)
WORKER_LATENCY = Histogram(
    "worker_processing_latency_seconds",
    "Total message processing time from receipt to ack",
)
```

- [ ] **Step 4: Modify `services/feature-worker/app/consumer.py` to add metrics instrumentation**

Full file content after modifications:

```python
import json
import logging
import time
import httpx
import aio_pika
from aio_pika import Message, DeliveryMode

from . import clients
from .mapping import EVENT_DELTA_MAP
from .metrics import (
    WORKER_PROCESSED_TOTAL,
    WORKER_FAILED_TOTAL,
    WORKER_RETRY_TOTAL,
    WORKER_DLQ_TOTAL,
    WORKER_LATENCY,
)

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "user.events"
ROUTING_KEY = "user.interaction"
DLQ_NAME = "feature.update.dlq"
MAX_RETRIES = 3


async def handle_message(
    message: aio_pika.IncomingMessage,
    exchange: aio_pika.abc.AbstractExchange,
    default_exchange: aio_pika.abc.AbstractExchange,
) -> None:
    start = time.time()
    try:
        await _process_message(message, exchange, default_exchange)
    finally:
        WORKER_LATENCY.observe(time.time() - start)


async def _process_message(
    message: aio_pika.IncomingMessage,
    exchange: aio_pika.abc.AbstractExchange,
    default_exchange: aio_pika.abc.AbstractExchange,
) -> None:
    try:
        body = json.loads(message.body)
        event_id = body["event_id"]
        user_id = body["user_id"]
        video_id = body["video_id"]
        event_type = body["event_type"]
        completion_rate = body.get("completion_rate")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error(json.dumps({"action": "skip", "reason": "invalid_schema", "error": str(exc)}))
        await message.ack()
        return

    delta = EVENT_DELTA_MAP.get(event_type)
    if delta is None:
        logger.error(json.dumps({
            "action": "skip", "reason": "unknown_event_type",
            "event_id": event_id, "event_type": event_type,
        }))
        await message.ack()
        return

    try:
        video = await clients.get_video(video_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.error(json.dumps({"action": "skip", "reason": "video_not_found", "event_id": event_id}))
            await message.ack()
            return
        if exc.response.status_code // 100 == 4:
            logger.error(json.dumps({
                "action": "skip", "reason": "video_client_error",
                "status": exc.response.status_code, "event_id": event_id,
            }))
            await message.ack()
            return
        await _handle_retry(message, exchange, default_exchange)
        return
    except httpx.HTTPError:
        await _handle_retry(message, exchange, default_exchange)
        return

    tags = video.get("tags", [])
    completion_rate_sample = completion_rate if delta.use_completion_rate else None

    needs_stats_patch = (
        delta.views_delta != 0
        or delta.likes_delta != 0
        or delta.skips_delta != 0
        or completion_rate_sample is not None
    )
    if needs_stats_patch:
        try:
            await clients.patch_video_stats(video_id, {
                "views_delta": delta.views_delta,
                "likes_delta": delta.likes_delta,
                "skips_delta": delta.skips_delta,
                "completion_rate_sample": completion_rate_sample,
            })
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code // 100 == 5:
                await _handle_retry(message, exchange, default_exchange)
                return
            logger.error(json.dumps({
                "action": "skip", "reason": "video_stats_error",
                "status": exc.response.status_code, "event_id": event_id,
            }))
            await message.ack()
            return
        except httpx.HTTPError:
            await _handle_retry(message, exchange, default_exchange)
            return

    for tag in tags:
        try:
            await clients.patch_user_interest(user_id, tag, delta.interest_delta)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.error(json.dumps({"action": "skip", "reason": "user_not_found", "event_id": event_id}))
                await message.ack()
                return
            if exc.response.status_code // 100 == 5:
                await _handle_retry(message, exchange, default_exchange)
                return
            logger.error(json.dumps({
                "action": "skip", "reason": "interest_error",
                "status": exc.response.status_code, "event_id": event_id,
            }))
            await message.ack()
            return
        except httpx.HTTPError:
            await _handle_retry(message, exchange, default_exchange)
            return

    await message.ack()
    WORKER_PROCESSED_TOTAL.inc()


async def _handle_retry(
    message: aio_pika.IncomingMessage,
    exchange: aio_pika.abc.AbstractExchange,
    default_exchange: aio_pika.abc.AbstractExchange,
) -> None:
    retry_count = int(message.headers.get("x-retry-count", 0))
    if retry_count < MAX_RETRIES:
        new_message = Message(
            body=message.body,
            content_type=message.content_type,
            delivery_mode=DeliveryMode.PERSISTENT,
            headers={"x-retry-count": retry_count + 1},
        )
        await exchange.publish(new_message, routing_key=ROUTING_KEY)
        logger.warning(json.dumps({"action": "retry", "x-retry-count": retry_count + 1}))
        WORKER_RETRY_TOTAL.inc()
    else:
        dead_message = Message(body=message.body, delivery_mode=DeliveryMode.PERSISTENT)
        await default_exchange.publish(dead_message, routing_key=DLQ_NAME)
        logger.error(json.dumps({"action": "dlq", "x-retry-count": retry_count}))
        WORKER_DLQ_TOTAL.inc()
        WORKER_FAILED_TOTAL.inc()
    await message.ack()
```

Note: `handle_message` now delegates to `_process_message` and wraps it in a `try/finally` for latency tracking. `WORKER_PROCESSED_TOTAL` is incremented only inside `_process_message` after the final `message.ack()` on the success path. `WORKER_FAILED_TOTAL` and `WORKER_DLQ_TOTAL` are incremented together in `_handle_retry` only when max retries are exhausted.

- [ ] **Step 5: Modify `services/feature-worker/app/main.py` to add `start_metrics_server`**

Full file content:

```python
import asyncio
import logging
import os
import aio_pika
from prometheus_client import start_http_server

from . import consumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://feedflow:feedflow@localhost:5672/")
EXCHANGE_NAME = "user.events"
QUEUE_NAME = "feature.update.queue"
DLQ_NAME = "feature.update.dlq"
ROUTING_KEY = "user.interaction"


def start_metrics_server() -> None:
    start_http_server(9100)


async def main() -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
    )
    await channel.declare_queue(DLQ_NAME, durable=True)
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    await queue.bind(exchange, routing_key=ROUTING_KEY)

    default_exchange = channel.default_exchange

    async def on_message(message: aio_pika.IncomingMessage) -> None:
        await consumer.handle_message(message, exchange, default_exchange)

    await queue.consume(on_message)
    logger.info("Feature Worker started — consuming from %s", QUEUE_NAME)

    await asyncio.Future()  # run until cancelled


if __name__ == "__main__":
    start_metrics_server()
    asyncio.run(main())
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd services/feature-worker && pytest tests/test_metrics.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 7: Verify existing tests still pass**

The existing `test_consumer.py` imports `handle_message` from `app.consumer`. After the refactor, `handle_message` is a thin wrapper that calls `_process_message`. The existing tests should still pass because `_process_message` contains the same logic as the old `handle_message`.

```bash
cd services/feature-worker && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add services/feature-worker/app/metrics.py \
        services/feature-worker/app/consumer.py \
        services/feature-worker/app/main.py \
        services/feature-worker/tests/test_metrics.py
git commit -m "feat(feature-worker): add Prometheus metrics and start_http_server on port 9100"
```

---

## Task 8: Infrastructure — Prometheus, Grafana, Docker Compose

**Files:**
- Create: `infra/prometheus/prometheus.yml`
- Create: `infra/grafana/provisioning/datasources/datasource.yml`
- Create: `infra/grafana/provisioning/dashboards/dashboard.yml`
- Create: `infra/grafana/dashboards/feedflow.json`
- Modify: `infra/docker-compose.yml`

### Background

All volume paths in docker-compose.yml are relative to `infra/docker-compose.yml`, so `./prometheus/prometheus.yml` maps to `infra/prometheus/prometheus.yml`. The datasource is given a fixed UID (`feedflow-prometheus`) so the dashboard JSON can reference it directly without template variables. Feature Worker uses `expose: ["9100"]` (not `ports:`) so Prometheus can reach it inside Docker network without publishing to the host.

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p infra/prometheus \
         infra/grafana/provisioning/datasources \
         infra/grafana/provisioning/dashboards \
         infra/grafana/dashboards
```

- [ ] **Step 2: Create `infra/prometheus/prometheus.yml`**

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "feed-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["feed-service:8005"]

  - job_name: "ranking-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["ranking-service:8004"]

  - job_name: "event-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["event-service:8003"]

  - job_name: "user-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["user-service:8001"]

  - job_name: "video-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["video-service:8002"]

  - job_name: "feature-worker"
    metrics_path: /metrics
    static_configs:
      - targets: ["feature-worker:9100"]
```

- [ ] **Step 3: Create `infra/grafana/provisioning/datasources/datasource.yml`**

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    uid: feedflow-prometheus
    url: http://prometheus:9090
    isDefault: true
```

- [ ] **Step 4: Create `infra/grafana/provisioning/dashboards/dashboard.yml`**

```yaml
apiVersion: 1
providers:
  - name: FeedFlow
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

- [ ] **Step 5: Create `infra/grafana/dashboards/feedflow.json`**

```json
{
  "title": "FeedFlow",
  "uid": "feedflow",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "30s",
  "time": { "from": "now-1h", "to": "now" },
  "tags": ["feedflow"],
  "panels": [
    {
      "id": 1,
      "title": "Feed Request Rate",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(feed_request_total[1m])",
          "legendFormat": "{{method}} {{route}} {{status}}",
          "refId": "A"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 2,
      "title": "Feed Latency p50 / p99",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "histogram_quantile(0.99, sum(rate(feed_request_latency_seconds_bucket[5m])) by (le))",
          "legendFormat": "p99",
          "refId": "A"
        },
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "histogram_quantile(0.50, sum(rate(feed_request_latency_seconds_bucket[5m])) by (le))",
          "legendFormat": "p50",
          "refId": "B"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "s" }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 3,
      "title": "Cache Hit Rate",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 8 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(feed_cache_hit_total[1m]) / clamp_min(rate(feed_cache_hit_total[1m]) + rate(feed_cache_miss_total[1m]), 0.001)",
          "legendFormat": "hit rate",
          "refId": "A"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "percentunit", "min": 0, "max": 1 }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 4,
      "title": "Feed Fallback Rate",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 8 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(feed_fallback_total[1m])",
          "legendFormat": "fallback/s",
          "refId": "A"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 5,
      "title": "Ranking Latency p50 / p99",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 16 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "histogram_quantile(0.99, sum(rate(ranking_request_latency_seconds_bucket[5m])) by (le))",
          "legendFormat": "p99",
          "refId": "A"
        },
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "histogram_quantile(0.50, sum(rate(ranking_request_latency_seconds_bucket[5m])) by (le))",
          "legendFormat": "p50",
          "refId": "B"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "s" }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 6,
      "title": "Ranking Candidate Count p99",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 16 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "histogram_quantile(0.99, sum(rate(ranking_candidate_count_bucket[5m])) by (le))",
          "legendFormat": "p99 candidates",
          "refId": "A"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 7,
      "title": "Event Ingest Rate",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 24 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(event_ingest_total[1m])",
          "legendFormat": "ingest/s",
          "refId": "A"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 8,
      "title": "Event Publish Success vs Failure",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 24 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(event_publish_success_total[1m])",
          "legendFormat": "success/s",
          "refId": "A"
        },
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(event_publish_failure_total[1m])",
          "legendFormat": "failure/s",
          "refId": "B"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 9,
      "title": "Event Publish Failure Rate",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 32 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(event_publish_failure_total[1m]) / clamp_min(rate(event_publish_success_total[1m]) + rate(event_publish_failure_total[1m]), 0.001)",
          "legendFormat": "failure rate",
          "refId": "A"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "percentunit", "min": 0, "max": 1 }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 10,
      "title": "Worker Processed / Retry / DLQ Rate",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 32 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(worker_message_processed_total[1m])",
          "legendFormat": "processed/s",
          "refId": "A"
        },
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(worker_retry_total[1m])",
          "legendFormat": "retry/s",
          "refId": "B"
        },
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "rate(worker_dlq_total[1m])",
          "legendFormat": "dlq/s",
          "refId": "C"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 11,
      "title": "Worker Processing Latency p99",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 40 },
      "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "feedflow-prometheus" },
          "expr": "histogram_quantile(0.99, sum(rate(worker_processing_latency_seconds_bucket[5m])) by (le))",
          "legendFormat": "p99",
          "refId": "A"
        }
      ],
      "fieldConfig": { "defaults": { "color": { "mode": "palette-classic" }, "unit": "s" }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    }
  ]
}
```

- [ ] **Step 6: Update `infra/docker-compose.yml`**

Add the `expose` directive to `feature-worker` and append `prometheus` and `grafana` services. Full file content after modifications:

```yaml
services:
  # ─── Databases ───────────────────────────────────────────────────────────────

  user-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: feedflow
      POSTGRES_PASSWORD: feedflow
      POSTGRES_DB: users
    ports:
      - "5436:5432"
    volumes:
      - user-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U feedflow -d users"]
      interval: 10s
      timeout: 5s
      retries: 5

  video-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: feedflow
      POSTGRES_PASSWORD: feedflow
      POSTGRES_DB: videos
    ports:
      - "5437:5432"
    volumes:
      - video-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U feedflow -d videos"]
      interval: 10s
      timeout: 5s
      retries: 5

  event-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: feedflow
      POSTGRES_PASSWORD: feedflow
      POSTGRES_DB: events
    ports:
      - "5438:5432"
    volumes:
      - event-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U feedflow -d events"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ─── Message Broker ──────────────────────────────────────────────────────────

  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: feedflow
      RABBITMQ_DEFAULT_PASS: feedflow
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ─── Application Services ────────────────────────────────────────────────────

  user-service:
    build:
      context: ../services/user-service
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: postgresql+asyncpg://feedflow:feedflow@user-db:5432/users
    depends_on:
      user-db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8001/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5

  video-service:
    build:
      context: ../services/video-service
    ports:
      - "8002:8002"
    environment:
      DATABASE_URL: postgresql+asyncpg://feedflow:feedflow@video-db:5432/videos
    depends_on:
      video-db:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8002/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 5

  event-service:
    build:
      context: ../services/event-service
    ports:
      - "8003:8003"
    environment:
      DATABASE_URL: postgresql+asyncpg://feedflow:feedflow@event-db:5432/events
      RABBITMQ_URL: amqp://feedflow:feedflow@rabbitmq:5672/
    depends_on:
      event-db:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy

  ranking-service:
    build:
      context: ../services/ranking-service
    ports:
      - "8004:8004"
    environment:
      USER_SERVICE_URL: http://user-service:8001
      VIDEO_SERVICE_URL: http://video-service:8002
    depends_on:
      - user-service
      - video-service

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
      video-service:
        condition: service_started
      ranking-service:
        condition: service_started
      redis:
        condition: service_healthy

  feature-worker:
    build:
      context: ../services/feature-worker
    expose:
      - "9100"
    environment:
      RABBITMQ_URL: amqp://feedflow:feedflow@rabbitmq:5672/
      USER_SERVICE_URL: http://user-service:8001
      VIDEO_SERVICE_URL: http://video-service:8002
    depends_on:
      rabbitmq:
        condition: service_healthy
      user-service:
        condition: service_healthy
      video-service:
        condition: service_healthy

  # ─── Observability ───────────────────────────────────────────────────────────

  prometheus:
    image: prom/prometheus:v2.51.0
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    depends_on:
      - feed-service
      - ranking-service
      - event-service
      - user-service
      - video-service
      - feature-worker

  grafana:
    image: grafana/grafana:10.4.0
    ports:
      - "3000:3000"
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
    depends_on:
      - prometheus

volumes:
  user-db-data:
  video-db-data:
  event-db-data:
```

- [ ] **Step 7: Verify the JSON is valid**

```bash
python3 -c "import json; json.load(open('infra/grafana/dashboards/feedflow.json')); print('JSON valid')"
```

Expected output: `JSON valid`

- [ ] **Step 8: Commit**

```bash
git add infra/prometheus/prometheus.yml \
        infra/grafana/provisioning/datasources/datasource.yml \
        infra/grafana/provisioning/dashboards/dashboard.yml \
        infra/grafana/dashboards/feedflow.json \
        infra/docker-compose.yml
git commit -m "feat(infra): add Prometheus and Grafana with 11-panel FeedFlow dashboard"
```

---

## Manual Verification Checklist (requires running stack)

After `docker compose -f infra/docker-compose.yml up --build`:

- [ ] `curl http://localhost:9090/targets` — all 6 targets show `state: "up"`
- [ ] `curl http://localhost:8005/feed/<any-user-id>` twice — second response should have `source: "cache_hit"`
- [ ] Open `http://localhost:3000` (admin/admin) — FeedFlow dashboard loads with 11 panels
- [ ] Cache Hit Rate panel shows a value (not NaN) immediately after first feed request
- [ ] `curl http://localhost:8005/metrics` — response contains `feed_request_total`, `feed_cache_hit_total`
- [ ] `curl http://localhost:8001/metrics` — response contains `user_request_total`
- [ ] Verify `/metrics` path is NOT in `feed_request_total` labels in the Prometheus UI
