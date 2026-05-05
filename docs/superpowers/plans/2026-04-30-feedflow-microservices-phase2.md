# FeedFlow Microservices Phase 2 — Event-Driven Feature Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Phase 1 microservices with an async event pipeline: Event Service publishes user interactions to RabbitMQ, a new Feature Worker consumes them and updates user interest scores and video statistics via the domain service APIs.

**Architecture:** Event Service inserts to event-db, returns 201, then fires a BackgroundTask to publish to RabbitMQ exchange `user.events`. Feature Worker consumes from `feature.update.queue`, calls `PATCH /videos/{id}/stats` and `PATCH /users/{id}/interests/{tag}` on the owning services, and implements manual retry via `x-retry-count` header with DLQ routing after 3 failures.

**Tech Stack:** Python 3.11, FastAPI, aio-pika 9.4.3, httpx 0.28.1, RabbitMQ 3.13, SQLAlchemy 2 async, PostgreSQL 16, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-04-30-feedflow-microservices-phase2-design.md`

**Working directory for all tasks:** `/Users/jiaxin/ClaudeProjects/feedflow-microservices/`

---

## File Map

**User Service (modify):**
- `services/user-service/app/schemas.py` — add `InterestDelta`
- `services/user-service/app/routes.py` — add `PATCH /users/{user_id}/interests/{tag}`
- `services/user-service/tests/test_routes.py` — new unit test file

**Video Service (modify):**
- `services/video-service/app/schemas.py` — add `StatsDelta`, `StatsResponse`
- `services/video-service/app/routes.py` — add `PATCH /videos/{video_id}/stats`
- `services/video-service/tests/test_routes.py` — new unit test file

**Event Service (modify):**
- `services/event-service/requirements.txt` — add `aio-pika==9.4.3`
- `services/event-service/app/publisher.py` — new: aio-pika connection + `publish_event()`
- `services/event-service/app/routes.py` — add `BackgroundTasks` param, enqueue only on `status: "created"`
- `services/event-service/app/main.py` — connect/disconnect RabbitMQ in lifespan
- `services/event-service/tests/test_publisher.py` — new unit test file

**Feature Worker (create new service):**
- `services/feature-worker/requirements.txt`
- `services/feature-worker/pytest.ini`
- `services/feature-worker/Dockerfile`
- `services/feature-worker/app/__init__.py`
- `services/feature-worker/app/mapping.py` — `EventDelta` dataclass + `EVENT_DELTA_MAP`
- `services/feature-worker/app/clients.py` — httpx calls to User Service and Video Service
- `services/feature-worker/app/consumer.py` — message handler, retry logic, DLQ routing
- `services/feature-worker/app/main.py` — RabbitMQ setup, topology declaration, consume loop
- `services/feature-worker/tests/__init__.py`
- `services/feature-worker/tests/test_mapping.py`
- `services/feature-worker/tests/test_consumer.py`

**Infrastructure (modify):**
- `infra/docker-compose.yml` — add `rabbitmq` + `feature-worker`, add healthchecks to `user-service` + `video-service`, add `RABBITMQ_URL` to `event-service`

**Integration tests (create):**
- `tests/integration/test_feature_pipeline.py`

---

## Task 1: User Service — PATCH /users/{user_id}/interests/{tag}

**Files:**
- Modify: `services/user-service/app/schemas.py`
- Modify: `services/user-service/app/routes.py`
- Create: `services/user-service/tests/test_routes.py`

### Step 1.1 — Write failing tests

Create `services/user-service/tests/test_routes.py`:

```python
import pytest
from contextlib import contextmanager
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.database import get_db


@contextmanager
def _make_client(mock_session):
    async def override_get_db():
        yield mock_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _user_exists():
    r = MagicMock()
    r.scalar_one_or_none.return_value = MagicMock(id="u1")
    return r


def _no_user():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _interest_exists(score: float):
    r = MagicMock()
    m = MagicMock()
    m.score = score
    r.scalar_one_or_none.return_value = m
    return r


def _no_interest():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _final_interest(tag: str, score: float):
    r = MagicMock()
    m = MagicMock()
    m.tag = tag
    m.score = score
    r.scalar_one.return_value = m
    return r


# --- tests ---

def test_patch_interest_applies_positive_delta():
    """Existing row score=0.5 + delta=0.1 → 0.6 returned."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _interest_exists(0.5),
        MagicMock(),                   # upsert (no return)
        _final_interest("ai", 0.6),    # re-fetch
    ])
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.1})
        assert resp.status_code == 200
        assert resp.json() == {"tag": "ai", "score": 0.6}


def test_patch_interest_clamped_at_1():
    """Score 0.95 + delta 0.2 → clamped to 1.0."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _interest_exists(0.95),
        MagicMock(),
        _final_interest("ai", 1.0),
    ])
    for client in _make_client(db):
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.2})
        assert resp.status_code == 200
        assert resp.json()["score"] == 1.0


def test_patch_interest_clamped_at_0():
    """Score 0.05 + delta -0.2 → clamped to 0.0."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _interest_exists(0.05),
        MagicMock(),
        _final_interest("ai", 0.0),
    ])
    for client in _make_client(db):
        resp = client.patch("/users/u1/interests/ai", json={"delta": -0.2})
        assert resp.status_code == 200
        assert resp.json()["score"] == 0.0


def test_patch_interest_no_row_positive_delta_creates():
    """No existing row, delta > 0 → creates row."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _no_interest(),
        MagicMock(),
        _final_interest("ai", 0.1),
    ])
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.1})
        assert resp.status_code == 200
        assert resp.json() == {"tag": "ai", "score": 0.1}
        db.commit.assert_awaited_once()


def test_patch_interest_no_row_negative_delta_no_write():
    """No existing row, delta <= 0 → returns score=0.0 without any DB write."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _user_exists(),
        _no_interest(),
    ])
    for client in _make_client(db):
        resp = client.patch("/users/u1/interests/ai", json={"delta": -0.08})
        assert resp.status_code == 200
        assert resp.json() == {"tag": "ai", "score": 0.0}
        db.commit.assert_not_awaited()


def test_patch_interest_user_not_found():
    """User missing → 404."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_no_user())
    with _make_client(db) as client:
        resp = client.patch("/users/u1/interests/ai", json={"delta": 0.1})
        assert resp.status_code == 404
```

- [ ] **Step 1.2 — Run tests to verify they fail**

```bash
cd services/user-service && pytest tests/test_routes.py -v
```

Expected: `ImportError` or `AttributeError` — `InterestDelta` not defined, PATCH route not found.

- [ ] **Step 1.3 — Add `InterestDelta` to schemas.py**

Open `services/user-service/app/schemas.py` and append:

```python
class InterestDelta(BaseModel):
    delta: float
```

- [ ] **Step 1.4 — Add PATCH endpoint to routes.py**

At the top of `services/user-service/app/routes.py`, add to the existing imports:

```python
from sqlalchemy import func, literal
from .schemas import UserCreate, UserResponse, InterestCreate, InterestResponse, InterestDelta
```

Then append this route to `services/user-service/app/routes.py`:

```python
@router.patch("/users/{user_id}/interests/{tag}", response_model=InterestResponse)
async def patch_interest(user_id: str, tag: str, body: InterestDelta, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)

    user_result = await db.execute(select(User).where(User.id == user_id))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    existing_result = await db.execute(
        select(UserInterest).where(UserInterest.user_id == user_id, UserInterest.tag == tag)
    )
    existing = existing_result.scalar_one_or_none()

    if existing is None and body.delta <= 0:
        return InterestResponse(tag=tag, score=0.0)

    new_score_for_insert = max(0.0, min(1.0, body.delta))

    stmt = (
        pg_insert(UserInterest)
        .values(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tag=tag,
            score=new_score_for_insert,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "tag"],
            set_=dict(
                score=func.greatest(
                    literal(0.0),
                    func.least(
                        literal(1.0),
                        UserInterest.__table__.c.score + body.delta,
                    ),
                ),
                updated_at=now,
            ),
        )
    )
    await db.execute(stmt)
    await db.commit()

    final_result = await db.execute(
        select(UserInterest).where(UserInterest.user_id == user_id, UserInterest.tag == tag)
    )
    return final_result.scalar_one()
```

- [ ] **Step 1.5 — Run tests to verify they pass**

```bash
cd services/user-service && pytest tests/test_routes.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 1.6 — Commit**

```bash
git add services/user-service/app/schemas.py services/user-service/app/routes.py services/user-service/tests/test_routes.py
git commit -m "feat(user-service): add PATCH /users/{user_id}/interests/{tag} with delta-based scoring"
```

---

## Task 2: Video Service — PATCH /videos/{video_id}/stats

**Files:**
- Modify: `services/video-service/app/schemas.py`
- Modify: `services/video-service/app/routes.py`
- Create: `services/video-service/tests/test_routes.py`

- [ ] **Step 2.1 — Write failing tests**

Create `services/video-service/tests/test_routes.py`:

```python
import pytest
from contextlib import contextmanager
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.database import get_db


@contextmanager
def _make_client(mock_session):
    async def override_get_db():
        yield mock_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _video_exists():
    r = MagicMock()
    r.scalar_one_or_none.return_value = MagicMock(id="v1")
    return r


def _no_video():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _stats_row(views=10, likes=2, skips=1, completion_rate=0.5):
    row = MagicMock()
    row.views = views
    row.likes = likes
    row.skips = skips
    row.completion_rate = completion_rate
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def test_patch_stats_applies_likes_delta():
    """likes_delta=+1 → response has incremented likes."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_video_exists(), _stats_row(views=5, likes=3, skips=1, completion_rate=0.4)])
    with _make_client(db) as client:
        resp = client.patch("/videos/v1/stats", json={
            "views_delta": 0, "likes_delta": 1, "skips_delta": 0, "completion_rate_sample": None
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["likes"] == 3
        assert body["views"] == 5


def test_patch_stats_complete_event():
    """views_delta=1, completion_rate_sample=0.8 → response reflects updated values."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _video_exists(),
        _stats_row(views=11, likes=0, skips=0, completion_rate=0.84),
    ])
    with _make_client(db) as client:
        resp = client.patch("/videos/v1/stats", json={
            "views_delta": 1, "likes_delta": 0, "skips_delta": 0, "completion_rate_sample": 0.8
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["views"] == 11
        assert body["completion_rate"] == pytest.approx(0.84)


def test_patch_stats_video_not_found():
    """Video missing → 404."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_no_video())
    with _make_client(db) as client:
        resp = client.patch("/videos/v1/stats", json={
            "views_delta": 0, "likes_delta": 1, "skips_delta": 0, "completion_rate_sample": None
        })
        assert resp.status_code == 404


def test_patch_stats_no_completion_rate_when_null():
    """completion_rate_sample=null → response completion_rate unchanged."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _video_exists(),
        _stats_row(views=5, likes=1, skips=0, completion_rate=0.5),
    ])
    with _make_client(db) as client:
        resp = client.patch("/videos/v1/stats", json={
            "views_delta": 0, "likes_delta": 1, "skips_delta": 0, "completion_rate_sample": None
        })
        assert resp.status_code == 200
        assert resp.json()["completion_rate"] == 0.5
```

- [ ] **Step 2.2 — Run tests to verify they fail**

```bash
cd services/video-service && pytest tests/test_routes.py -v
```

Expected: `ImportError` — `StatsDelta` not defined, PATCH route not found.

- [ ] **Step 2.3 — Add `StatsDelta` and `StatsResponse` to schemas.py**

Open `services/video-service/app/schemas.py` and append:

```python
class StatsDelta(BaseModel):
    views_delta: int = 0
    likes_delta: int = 0
    skips_delta: int = 0
    completion_rate_sample: float | None = None


class StatsResponse(BaseModel):
    views: int
    likes: int
    skips: int
    completion_rate: float
```

- [ ] **Step 2.4 — Add PATCH endpoint to routes.py**

Add to existing imports at the top of `services/video-service/app/routes.py`:

```python
from sqlalchemy import select, update
from .schemas import VideoCreate, VideoResponse, StatsDelta, StatsResponse
```

Then append this route (after all existing routes):

```python
@router.patch("/videos/{video_id}/stats", response_model=StatsResponse)
async def patch_stats(video_id: str, body: StatsDelta, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Video not found")

    values = {
        "views": VideoStats.views + body.views_delta,
        "likes": VideoStats.likes + body.likes_delta,
        "skips": VideoStats.skips + body.skips_delta,
        "updated_at": datetime.now(timezone.utc),
    }
    if body.completion_rate_sample is not None:
        # Uses pre-increment VideoStats.views (old value before views_delta is applied)
        values["completion_rate"] = (
            (VideoStats.completion_rate * VideoStats.views + body.completion_rate_sample)
            / (VideoStats.views + 1)
        )

    stmt = (
        update(VideoStats)
        .where(VideoStats.video_id == video_id)
        .values(**values)
        .returning(
            VideoStats.views,
            VideoStats.likes,
            VideoStats.skips,
            VideoStats.completion_rate,
        )
    )
    result = await db.execute(stmt)
    row = result.fetchone()
    await db.commit()
    return StatsResponse(
        views=row.views,
        likes=row.likes,
        skips=row.skips,
        completion_rate=row.completion_rate,
    )
```

The existing import `from sqlalchemy import select` already exists; add `update` to that import line. Also verify `from .schemas import` includes the new names.

- [ ] **Step 2.5 — Run tests to verify they pass**

```bash
cd services/video-service && pytest tests/test_routes.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 2.6 — Commit**

```bash
git add services/video-service/app/schemas.py services/video-service/app/routes.py services/video-service/tests/test_routes.py
git commit -m "feat(video-service): add PATCH /videos/{video_id}/stats with atomic SQL update"
```

---

## Task 3: Event Service — RabbitMQ Publisher + BackgroundTask

**Files:**
- Modify: `services/event-service/requirements.txt`
- Create: `services/event-service/app/publisher.py`
- Modify: `services/event-service/app/routes.py`
- Modify: `services/event-service/app/main.py`
- Create: `services/event-service/tests/test_publisher.py`

- [ ] **Step 3.1 — Write failing tests**

Create `services/event-service/tests/test_publisher.py`:

```python
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
```

Also create `services/event-service/tests/test_routes_publisher.py` to verify BackgroundTask behavior:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.database import get_db


def _committed_db(event_id="evt-1"):
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


def _duplicate_db():
    db = AsyncMock()
    exc = IntegrityError(None, None, Exception("duplicate"))
    exc.orig = MagicMock()
    exc.orig.pgcode = "23505"
    db.commit = AsyncMock(side_effect=exc)
    return db


def test_created_event_enqueues_background_task():
    """A newly created event (status=created) triggers publish_event via BackgroundTask."""
    db = _committed_db()

    async def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db

    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock) as mock_publish:
        with TestClient(app) as client:
            resp = client.post("/events", json={
                "user_id": "u-1",
                "video_id": "v-1",
                "event_type": "like",
                "idempotency_key": "key-001",
            })
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"
        mock_publish.assert_awaited_once()
        call_kwargs = mock_publish.await_args[0][0]
        assert call_kwargs["event_type"] == "like"
        assert call_kwargs["user_id"] == "u-1"

    app.dependency_overrides.clear()


def test_duplicate_event_does_not_enqueue_background_task():
    """A duplicate event (status=duplicate_ignored) must NOT call publish_event."""
    db = _duplicate_db()

    async def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db

    with patch("app.routes.publisher.publish_event", new_callable=AsyncMock) as mock_publish:
        with TestClient(app) as client:
            resp = client.post("/events", json={
                "user_id": "u-1",
                "video_id": "v-1",
                "event_type": "like",
                "idempotency_key": "key-dup",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "duplicate_ignored"
        mock_publish.assert_not_awaited()

    app.dependency_overrides.clear()
```

- [ ] **Step 3.2 — Run tests to verify they fail**

```bash
cd services/event-service && pytest tests/test_publisher.py tests/test_routes_publisher.py -v
```

Expected: `ModuleNotFoundError` for `aio_pika` or `ImportError` for `publisher`.

- [ ] **Step 3.3 — Add aio-pika to requirements.txt**

Edit `services/event-service/requirements.txt` to add `aio-pika==9.4.3`:

```
fastapi==0.115.5
uvicorn==0.32.1
sqlalchemy==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
aio-pika==9.4.3
```

- [ ] **Step 3.4 — Install aio-pika locally for tests**

```bash
cd services/event-service && pip install aio-pika==9.4.3
```

- [ ] **Step 3.5 — Create publisher.py**

Create `services/event-service/app/publisher.py`:

```python
import os
import json
import logging
import aio_pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "")
EXCHANGE_NAME = "user.events"
ROUTING_KEY = "user.interaction"

_connection = None
_channel = None
_exchange = None


async def connect() -> None:
    global _connection, _channel, _exchange
    _connection = await aio_pika.connect_robust(RABBITMQ_URL)
    _channel = await _connection.channel()
    _exchange = await _channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
    )


async def disconnect() -> None:
    global _connection
    if _connection:
        await _connection.close()
        _connection = None


async def publish_event(event_data: dict) -> None:
    if _exchange is None:
        logger.error("RabbitMQ not connected; skipping publish for event_id=%s", event_data.get("event_id"))
        return
    try:
        message = aio_pika.Message(
            body=json.dumps(event_data).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await _exchange.publish(message, routing_key=ROUTING_KEY)
    except Exception as exc:
        logger.error(
            "publish_failed event_id=%s idempotency_key=%s error=%s",
            event_data.get("event_id"),
            event_data.get("idempotency_key"),
            str(exc),
        )
```

- [ ] **Step 3.6 — Update routes.py to add BackgroundTask**

Replace the entire `services/event-service/app/routes.py` with:

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

router = APIRouter()


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
        background_tasks.add_task(publisher.publish_event, event_data)
        return JSONResponse(status_code=201, content={"id": event.id, "status": "created"})
    except IntegrityError as exc:
        await db.rollback()
        pg_code = getattr(exc.orig, "pgcode", None)
        if pg_code == "23505":
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

- [ ] **Step 3.7 — Update main.py to manage RabbitMQ connection in lifespan**

Replace `services/event-service/app/main.py` with:

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import engine, Base
from .routes import router
from . import publisher


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if os.environ.get("RABBITMQ_URL"):
        await publisher.connect()
    yield
    await publisher.disconnect()


app = FastAPI(title="Event Service", lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 3.8 — Run all event-service tests**

```bash
cd services/event-service && pytest tests/ -v
```

Expected: all tests PASS (existing schema tests + new publisher + routes_publisher tests).

- [ ] **Step 3.9 — Commit**

```bash
git add services/event-service/requirements.txt services/event-service/app/publisher.py services/event-service/app/routes.py services/event-service/app/main.py services/event-service/tests/test_publisher.py services/event-service/tests/test_routes_publisher.py
git commit -m "feat(event-service): publish events to RabbitMQ via BackgroundTask after successful insert"
```

---

## Task 4: Feature Worker — Scaffold + mapping.py

**Files:**
- Create: `services/feature-worker/requirements.txt`
- Create: `services/feature-worker/pytest.ini`
- Create: `services/feature-worker/Dockerfile`
- Create: `services/feature-worker/app/__init__.py`
- Create: `services/feature-worker/app/mapping.py`
- Create: `services/feature-worker/tests/__init__.py`
- Create: `services/feature-worker/tests/test_mapping.py`

- [ ] **Step 4.1 — Write failing tests**

Create `services/feature-worker/tests/test_mapping.py`:

```python
import pytest
from app.mapping import EVENT_DELTA_MAP, EventDelta


def test_watch_delta():
    d = EVENT_DELTA_MAP["watch"]
    assert d.views_delta == 0
    assert d.likes_delta == 0
    assert d.skips_delta == 0
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(0.02)


def test_like_delta():
    d = EVENT_DELTA_MAP["like"]
    assert d.views_delta == 0
    assert d.likes_delta == 1
    assert d.skips_delta == 0
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(0.10)


def test_skip_delta():
    d = EVENT_DELTA_MAP["skip"]
    assert d.views_delta == 0
    assert d.likes_delta == 0
    assert d.skips_delta == 1
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(-0.08)


def test_complete_delta():
    d = EVENT_DELTA_MAP["complete"]
    assert d.views_delta == 1
    assert d.likes_delta == 0
    assert d.skips_delta == 0
    assert d.use_completion_rate is True
    assert d.interest_delta == pytest.approx(0.06)


def test_share_delta():
    d = EVENT_DELTA_MAP["share"]
    assert d.views_delta == 0
    assert d.likes_delta == 0
    assert d.skips_delta == 0
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(0.08)


def test_comment_delta():
    d = EVENT_DELTA_MAP["comment"]
    assert d.views_delta == 0
    assert d.likes_delta == 0
    assert d.skips_delta == 0
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(0.04)


def test_all_six_event_types_present():
    assert set(EVENT_DELTA_MAP.keys()) == {"watch", "like", "skip", "complete", "share", "comment"}
```


- [ ] **Step 4.2 — Create scaffold files**

Create `services/feature-worker/requirements.txt`:

```
aio-pika==9.4.3
httpx==0.28.1
pytest==8.3.4
```

Create `services/feature-worker/pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = .
```

Create `services/feature-worker/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["python", "-m", "app.main"]
```

Create `services/feature-worker/app/__init__.py` (empty file).

Create `services/feature-worker/tests/__init__.py` (empty file).

- [ ] **Step 4.3 — Run tests to verify they fail**

```bash
cd services/feature-worker && pip install -r requirements.txt && pytest tests/test_mapping.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.mapping'`.

- [ ] **Step 4.4 — Create mapping.py**

Create `services/feature-worker/app/mapping.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EventDelta:
    views_delta: int
    likes_delta: int
    skips_delta: int
    use_completion_rate: bool
    interest_delta: float


EVENT_DELTA_MAP: dict[str, EventDelta] = {
    "watch":   EventDelta(views_delta=0, likes_delta=0, skips_delta=0, use_completion_rate=False, interest_delta=0.02),
    "like":    EventDelta(views_delta=0, likes_delta=1, skips_delta=0, use_completion_rate=False, interest_delta=0.10),
    "skip":    EventDelta(views_delta=0, likes_delta=0, skips_delta=1, use_completion_rate=False, interest_delta=-0.08),
    "complete": EventDelta(views_delta=1, likes_delta=0, skips_delta=0, use_completion_rate=True, interest_delta=0.06),
    "share":   EventDelta(views_delta=0, likes_delta=0, skips_delta=0, use_completion_rate=False, interest_delta=0.08),
    "comment": EventDelta(views_delta=0, likes_delta=0, skips_delta=0, use_completion_rate=False, interest_delta=0.04),
}
```

- [ ] **Step 4.5 — Run tests to verify they pass**

```bash
cd services/feature-worker && pytest tests/test_mapping.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 4.6 — Commit**

```bash
git add services/feature-worker/
git commit -m "feat(feature-worker): scaffold service with mapping.py delta table"
```

---

## Task 5: Feature Worker — clients.py

**Files:**
- Create: `services/feature-worker/app/clients.py`

No separate unit test file for clients — behavior is covered by consumer tests (Task 6).

- [ ] **Step 5.1 — Create clients.py**

Create `services/feature-worker/app/clients.py`:

```python
import os
import httpx

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:8001")
VIDEO_SERVICE_URL = os.environ.get("VIDEO_SERVICE_URL", "http://localhost:8002")


async def get_video(video_id: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{VIDEO_SERVICE_URL}/videos/{video_id}")
        response.raise_for_status()
        return response.json()


async def patch_video_stats(video_id: str, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.patch(
            f"{VIDEO_SERVICE_URL}/videos/{video_id}/stats",
            json=payload,
        )
        response.raise_for_status()


async def patch_user_interest(user_id: str, tag: str, delta: float) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.patch(
            f"{USER_SERVICE_URL}/users/{user_id}/interests/{tag}",
            json={"delta": delta},
        )
        response.raise_for_status()
```

- [ ] **Step 5.2 — Commit**

```bash
git add services/feature-worker/app/clients.py
git commit -m "feat(feature-worker): add httpx client functions for User Service and Video Service"
```

---

## Task 6: Feature Worker — consumer.py + unit tests

**Files:**
- Create: `services/feature-worker/app/consumer.py`
- Create: `services/feature-worker/tests/test_consumer.py`

- [ ] **Step 6.1 — Write failing tests**

Create `services/feature-worker/tests/test_consumer.py`:

```python
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


# --- tests ---

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
```

- [ ] **Step 6.2 — Run tests to verify they fail**

```bash
cd services/feature-worker && pytest tests/test_consumer.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.consumer'`.

- [ ] **Step 6.3 — Create consumer.py**

Create `services/feature-worker/app/consumer.py`:

```python
import json
import logging
import httpx
import aio_pika
from aio_pika import Message, DeliveryMode

from . import clients
from .mapping import EVENT_DELTA_MAP

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
    else:
        dead_message = Message(body=message.body, delivery_mode=DeliveryMode.PERSISTENT)
        await default_exchange.publish(dead_message, routing_key=DLQ_NAME)
        logger.error(json.dumps({"action": "dlq", "x-retry-count": retry_count}))
    await message.ack()
```

- [ ] **Step 6.4 — Run tests to verify they pass**

```bash
cd services/feature-worker && pytest tests/test_consumer.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 6.5 — Commit**

```bash
git add services/feature-worker/app/consumer.py services/feature-worker/tests/test_consumer.py
git commit -m "feat(feature-worker): add consumer.py with retry logic and DLQ routing"
```

---

## Task 7: Feature Worker — main.py

**Files:**
- Create: `services/feature-worker/app/main.py`

- [ ] **Step 7.1 — Create main.py**

Create `services/feature-worker/app/main.py`:

```python
import asyncio
import logging
import os
import aio_pika

from . import consumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://feedflow:feedflow@localhost:5672/")
EXCHANGE_NAME = "user.events"
QUEUE_NAME = "feature.update.queue"
DLQ_NAME = "feature.update.dlq"
ROUTING_KEY = "user.interaction"


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
    asyncio.run(main())
```

- [ ] **Step 7.2 — Run all feature-worker tests**

```bash
cd services/feature-worker && pytest tests/ -v
```

Expected: all tests PASS (mapping + consumer).

- [ ] **Step 7.3 — Commit**

```bash
git add services/feature-worker/app/main.py
git commit -m "feat(feature-worker): add main.py with RabbitMQ topology declaration and consume loop"
```

---

## Task 8: Docker Compose — RabbitMQ + feature-worker + healthchecks

**Files:**
- Modify: `infra/docker-compose.yml`

- [ ] **Step 8.1 — Update docker-compose.yml**

Replace the full content of `infra/docker-compose.yml` with:

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
    depends_on:
      - video-service
      - ranking-service

  feature-worker:
    build:
      context: ../services/feature-worker
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

volumes:
  user-db-data:
  video-db-data:
  event-db-data:
```

- [ ] **Step 8.2 — Validate compose file syntax**

```bash
docker compose -f infra/docker-compose.yml config --quiet
```

Expected: exits 0 (no output means valid).

- [ ] **Step 8.3 — Rebuild and start the stack**

```bash
docker compose -f infra/docker-compose.yml up --build -d
```

Wait ~30 seconds for all services to start and pass healthchecks.

- [ ] **Step 8.4 — Verify RabbitMQ and feature-worker are running**

```bash
docker compose -f infra/docker-compose.yml ps
```

Expected: all services in `running` or `healthy` state. Then check feature-worker logs:

```bash
docker compose -f infra/docker-compose.yml logs feature-worker
```

Expected: `Feature Worker started — consuming from feature.update.queue`

- [ ] **Step 8.5 — Commit**

```bash
git add infra/docker-compose.yml
git commit -m "feat(infra): add RabbitMQ, feature-worker, and healthchecks for user-service and video-service"
```

---

## Task 9: Integration Tests — Feature Pipeline

**Files:**
- Create: `tests/integration/test_feature_pipeline.py`

- [ ] **Step 9.1 — Write integration tests**

Create `tests/integration/test_feature_pipeline.py`:

```python
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
    assert score > 0.0, f"Expected positive interest score, got {score}"


def test_watch_event_does_not_increment_views():
    """POST watch event → video views remain unchanged (polled wait, then assert)."""
    user_id = _create_user()
    video_id = _create_video(user_id, tags=["ml"])

    initial_stats = _get_video_stats(video_id)
    initial_views = initial_stats["views"]

    _post_event(user_id, video_id, event_type="watch")

    # Give the pipeline time to settle; views must NOT increase
    time.sleep(2.0)

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
```

- [ ] **Step 9.2 — Verify Docker Compose stack is running**

```bash
docker compose -f infra/docker-compose.yml ps
```

Expected: all services healthy. If not, start it:

```bash
docker compose -f infra/docker-compose.yml up -d
```

Wait 30 seconds, then re-check.

- [ ] **Step 9.3 — Run Phase 1 integration tests to confirm no regressions**

```bash
pytest tests/integration/test_feed_flow.py tests/integration/test_service_health.py -v
```

Expected: all existing tests PASS.

- [ ] **Step 9.4 — Run Phase 2 integration tests**

```bash
pytest tests/integration/test_feature_pipeline.py -v
```

Expected: all 4 tests PASS. If a test fails due to timing, increase `timeout` in `poll_until` calls.

- [ ] **Step 9.5 — Commit**

```bash
git add tests/integration/test_feature_pipeline.py
git commit -m "test(integration): add Phase 2 feature pipeline integration tests with polling assertions"
```

---

## Self-Review Checklist

Before marking the plan complete, verify:

- [ ] All 9 Definition of Done criteria from the spec are covered by a task
- [ ] BackgroundTask added only on `status: "created"` — tested in `test_routes_publisher.py`
- [ ] `watch` event: stats PATCH skipped — tested in `test_watch_event_skips_stats_patch`
- [ ] `complete` event: `completion_rate` passed as sample — tested in `test_complete_event_passes_completion_rate`
- [ ] Negative delta on missing tag: no DB write, score=0.0 returned — tested in `test_patch_interest_no_row_negative_delta_no_write`
- [ ] Retry republishes to exchange (not direct to queue) — tested in `test_5xx_from_video_service_triggers_retry`
- [ ] DLQ routes via default exchange with routing_key=queue_name — tested in `test_exhausted_retries_route_to_dlq`
- [ ] Integration test polls (no fixed sleep except the 2s watch-views test) — confirmed in Task 9
- [ ] All Phase 1 integration tests re-run before declaring Phase 2 done (Step 9.3)
