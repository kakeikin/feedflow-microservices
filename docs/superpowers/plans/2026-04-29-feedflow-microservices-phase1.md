# FeedFlow Microservices Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `feedflow-microservices/` — five self-contained FastAPI microservices (user, video, event, ranking, feed) orchestrated with Docker Compose, each independently deployable with its own database.

**Architecture:** Three database-backed services (user, video, event) using SQLAlchemy 2 async + asyncpg. Two stateless services (ranking, feed) that call upstream services via httpx. All UUIDs generated in Python with `uuid.uuid4()`. Tables initialized via `create_all()` on startup. All httpx calls use `timeout=3.0`.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, SQLAlchemy 2 (async), asyncpg, httpx, Pydantic v2, pytest, Docker, Docker Compose, PostgreSQL 16.

**Repository location:** `/Users/jiaxin/ClaudeProjects/feedflow-microservices/`

---

## File Map

```
feedflow-microservices/
├── services/
│   ├── user-service/
│   │   ├── app/main.py, models.py, schemas.py, database.py, routes.py
│   │   ├── tests/test_schemas.py
│   │   ├── Dockerfile, requirements.txt, pytest.ini
│   ├── video-service/
│   │   ├── app/main.py, models.py, schemas.py, database.py, routes.py
│   │   ├── tests/test_schemas.py
│   │   ├── Dockerfile, requirements.txt, pytest.ini
│   ├── event-service/
│   │   ├── app/main.py, models.py, schemas.py, database.py, routes.py
│   │   ├── tests/test_schemas.py
│   │   ├── Dockerfile, requirements.txt, pytest.ini
│   ├── ranking-service/
│   │   ├── app/main.py, schemas.py, ranking.py, clients.py, routes.py
│   │   ├── tests/test_ranking.py
│   │   ├── Dockerfile, requirements.txt, pytest.ini
│   └── feed-service/
│       ├── app/main.py, schemas.py, clients.py, routes.py
│       ├── tests/test_routes.py
│       ├── Dockerfile, requirements.txt, pytest.ini
├── shared/
│   ├── schemas/common.py, events.py, feed.py
│   ├── logging/logger.py
│   └── config/settings.py
├── infra/docker-compose.yml
├── tests/
│   ├── integration/conftest.py
│   ├── integration/test_service_health.py
│   └── integration/test_feed_flow.py
├── pytest.ini
└── README.md
```

---

## Task 1: Initialize Repository Structure

**Files:**
- Create: `feedflow-microservices/` directory tree
- Create: `feedflow-microservices/.gitignore`
- Create: `feedflow-microservices/README.md` (stub)

- [ ] **Step 1: Create the repository and directory scaffold**

Run from `/Users/jiaxin/ClaudeProjects/`:
```bash
mkdir -p feedflow-microservices/services/user-service/app
mkdir -p feedflow-microservices/services/user-service/tests
mkdir -p feedflow-microservices/services/video-service/app
mkdir -p feedflow-microservices/services/video-service/tests
mkdir -p feedflow-microservices/services/event-service/app
mkdir -p feedflow-microservices/services/event-service/tests
mkdir -p feedflow-microservices/services/ranking-service/app
mkdir -p feedflow-microservices/services/ranking-service/tests
mkdir -p feedflow-microservices/services/feed-service/app
mkdir -p feedflow-microservices/services/feed-service/tests
mkdir -p feedflow-microservices/shared/schemas
mkdir -p feedflow-microservices/shared/logging
mkdir -p feedflow-microservices/shared/config
mkdir -p feedflow-microservices/infra
mkdir -p feedflow-microservices/tests/integration
mkdir -p feedflow-microservices/docs
```

- [ ] **Step 2: Create .gitignore**

Create `feedflow-microservices/.gitignore`:
```
__pycache__/
*.pyc
*.pyo
.env
.venv/
venv/
*.egg-info/
.pytest_cache/
.DS_Store
```

- [ ] **Step 3: Create README stub**

Create `feedflow-microservices/README.md`:
```markdown
# FeedFlow Microservices

FeedFlow Microservices is the second-generation version of FeedFlow.

The original FeedFlow was a monolithic personalized feed backend. This version redesigns the system into independently deployable services to improve fault isolation, maintainability, and scalability.

Phase 1 focuses on service decomposition, HTTP-based service communication, Docker Compose orchestration, and basic integration testing.

## Services

| Service | Port | Responsibility |
|---|---|---|
| user-service | 8001 | Users and interest profiles |
| video-service | 8002 | Video metadata and stats |
| event-service | 8003 | User interaction events |
| ranking-service | 8004 | Rule-based video scoring |
| feed-service | 8005 | Personalized feed API |

## Run Locally

```bash
docker compose -f infra/docker-compose.yml up --build
```

All services start with their databases. Tables are created automatically on first boot.

## Architecture

```
Client → Feed Service (8005)
           ├─ GET /videos/trending  → Video Service (8002)
           └─ POST /rank            → Ranking Service (8004)
                                         ├─ GET /users/{id}/interests → User Service (8001)
                                         └─ GET /videos/{id}          → Video Service (8002)

Client → Event Service (8003) → event-db
Client → User Service (8001)  → user-db
Client → Video Service (8002) → video-db
```

## Integration Tests

Assumes Docker Compose is running:
```bash
pytest tests/integration/ -v
```
```
```

- [ ] **Step 4: Create root pytest.ini**

Create `feedflow-microservices/pytest.ini`:
```ini
[pytest]
testpaths = tests
```

- [ ] **Step 5: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git init
git add .
git commit -m "chore: initialize feedflow-microservices repository structure"
```

---

## Task 2: User Service

**Files:**
- Create: `services/user-service/app/database.py`
- Create: `services/user-service/app/models.py`
- Create: `services/user-service/app/schemas.py`
- Create: `services/user-service/app/routes.py`
- Create: `services/user-service/app/__init__.py`
- Create: `services/user-service/app/main.py`
- Create: `services/user-service/tests/__init__.py`
- Create: `services/user-service/tests/test_schemas.py`
- Create: `services/user-service/requirements.txt`
- Create: `services/user-service/Dockerfile`
- Create: `services/user-service/pytest.ini`

- [ ] **Step 1: Write the failing schema tests**

Create `services/user-service/tests/__init__.py` (empty).

Create `services/user-service/tests/test_schemas.py`:
```python
import pytest
from pydantic import ValidationError


def test_user_create_valid():
    from app.schemas import UserCreate
    user = UserCreate(email="test@example.com", display_name="Test")
    assert user.email == "test@example.com"
    assert user.display_name == "Test"


def test_user_create_missing_email():
    from app.schemas import UserCreate
    with pytest.raises(ValidationError):
        UserCreate(display_name="Test")


def test_interest_create_valid():
    from app.schemas import InterestCreate
    interest = InterestCreate(tag="ai", score=0.9)
    assert interest.tag == "ai"
    assert interest.score == 0.9


def test_interest_create_missing_tag():
    from app.schemas import InterestCreate
    with pytest.raises(ValidationError):
        InterestCreate(score=0.9)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/user-service
pip install pydantic==2.10.3 pytest==8.3.4
pytest tests/test_schemas.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create requirements.txt and install dependencies**

Create `services/user-service/requirements.txt`:
```
fastapi==0.115.5
uvicorn==0.32.1
sqlalchemy==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
```

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: Create pytest.ini**

Create `services/user-service/pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 5: Create app/__init__.py**

Create `services/user-service/app/__init__.py` (empty).

- [ ] **Step 6: Write schemas.py**

Create `services/user-service/app/schemas.py`:
```python
from datetime import datetime
from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    display_name: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InterestCreate(BaseModel):
    tag: str
    score: float


class InterestResponse(BaseModel):
    tag: str
    score: float

    model_config = {"from_attributes": True}
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/user-service
pytest tests/test_schemas.py -v
```

Expected: 4 tests pass.

- [ ] **Step 8: Write database.py**

Create `services/user-service/app/database.py`:
```python
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 9: Write models.py**

Create `services/user-service/app/models.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class UserInterest(Base):
    __tablename__ = "user_interests"
    __table_args__ = (UniqueConstraint("user_id", "tag"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    tag: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

- [ ] **Step 10: Write routes.py**

Create `services/user-service/app/routes.py`:
```python
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .database import get_db
from .models import User, UserInterest
from .schemas import UserCreate, UserResponse, InterestCreate, InterestResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "user-service", "status": "ok"}


@router.post("/users", status_code=201, response_model=UserResponse)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        display_name=body.display_name,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    await db.commit()
    result = await db.execute(select(User).where(User.id == user.id))
    return result.scalar_one()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{user_id}/interests", response_model=list[InterestResponse])
async def get_interests(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserInterest).where(UserInterest.user_id == user_id)
    )
    return result.scalars().all()


@router.post("/users/{user_id}/interests", status_code=201, response_model=InterestResponse)
async def add_interest(user_id: str, body: InterestCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    stmt = pg_insert(UserInterest).values(
        id=str(uuid.uuid4()),
        user_id=user_id,
        tag=body.tag,
        score=body.score,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=["user_id", "tag"],
        set_={"score": body.score, "updated_at": now},
    )
    await db.execute(stmt)
    await db.commit()
    result = await db.execute(
        select(UserInterest).where(
            UserInterest.user_id == user_id,
            UserInterest.tag == body.tag,
        )
    )
    return result.scalar_one()
```

- [ ] **Step 11: Write main.py**

Create `services/user-service/app/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import engine, Base
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 12: Write Dockerfile**

Create `services/user-service/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

- [ ] **Step 13: Run unit tests one final time**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/user-service
pytest tests/ -v
```

Expected: 4 tests pass.

- [ ] **Step 14: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git add services/user-service/
git commit -m "feat: add user-service with users and interests endpoints"
```

---

## Task 3: Video Service

**Files:**
- Create: `services/video-service/app/__init__.py`
- Create: `services/video-service/app/database.py`
- Create: `services/video-service/app/models.py`
- Create: `services/video-service/app/schemas.py`
- Create: `services/video-service/app/routes.py`
- Create: `services/video-service/app/main.py`
- Create: `services/video-service/tests/__init__.py`
- Create: `services/video-service/tests/test_schemas.py`
- Create: `services/video-service/requirements.txt`
- Create: `services/video-service/Dockerfile`
- Create: `services/video-service/pytest.ini`

- [ ] **Step 1: Write failing schema tests**

Create `services/video-service/tests/__init__.py` (empty).

Create `services/video-service/tests/test_schemas.py`:
```python
import pytest
from pydantic import ValidationError


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


def test_video_create_missing_title():
    from app.schemas import VideoCreate
    with pytest.raises(ValidationError):
        VideoCreate(creator_id="u", tags=[], duration_seconds=60)


def test_video_stats_defaults():
    from app.schemas import VideoStatsResponse
    stats = VideoStatsResponse(views=0, likes=0, skips=0, completion_rate=0.0)
    assert stats.views == 0
    assert stats.completion_rate == 0.0
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/video-service
pip install pydantic==2.10.3 pytest==8.3.4
pytest tests/test_schemas.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create requirements.txt, pytest.ini, install**

Create `services/video-service/requirements.txt`:
```
fastapi==0.115.5
uvicorn==0.32.1
sqlalchemy==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
```

Create `services/video-service/pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
```

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: Create app/__init__.py and schemas.py**

Create `services/video-service/app/__init__.py` (empty).

Create `services/video-service/app/schemas.py`:
```python
from datetime import datetime
from pydantic import BaseModel


class VideoCreate(BaseModel):
    title: str
    creator_id: str
    tags: list[str]
    duration_seconds: int


class VideoStatsResponse(BaseModel):
    views: int
    likes: int
    skips: int
    completion_rate: float

    model_config = {"from_attributes": True}


class VideoResponse(BaseModel):
    id: str
    title: str
    creator_id: str
    tags: list[str]
    duration_seconds: int
    created_at: datetime
    stats: VideoStatsResponse

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Run to verify tests pass**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/video-service
pytest tests/test_schemas.py -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Write database.py**

Create `services/video-service/app/database.py`:
```python
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 7: Write models.py**

Create `services/video-service/app/models.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    creator_id: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    stats: Mapped["VideoStats"] = relationship(
        "VideoStats", back_populates="video", uselist=False, lazy="selectin"
    )


class VideoStats(Base):
    __tablename__ = "video_stats"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    video_id: Mapped[str] = mapped_column(String, ForeignKey("videos.id"), unique=True, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    skips: Mapped[int] = mapped_column(Integer, default=0)
    completion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    video: Mapped["Video"] = relationship("Video", back_populates="stats")
```

- [ ] **Step 8: Write routes.py**

Create `services/video-service/app/routes.py`:
```python
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .database import get_db
from .models import Video, VideoStats
from .schemas import VideoCreate, VideoResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "video-service", "status": "ok"}


@router.post("/videos", status_code=201, response_model=VideoResponse)
async def create_video(body: VideoCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    video_id = str(uuid.uuid4())
    video = Video(
        id=video_id,
        title=body.title,
        creator_id=body.creator_id,
        tags=body.tags,
        duration_seconds=body.duration_seconds,
        created_at=now,
    )
    db.add(video)
    # Atomic: create stats alongside video in same transaction
    stats = VideoStats(id=str(uuid.uuid4()), video_id=video_id, updated_at=now)
    db.add(stats)
    await db.commit()
    result = await db.execute(
        select(Video).options(selectinload(Video.stats)).where(Video.id == video_id)
    )
    return result.scalar_one()


@router.get("/videos", response_model=list[VideoResponse])
async def list_videos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).options(selectinload(Video.stats)))
    return result.scalars().all()


# IMPORTANT: /videos/trending must be defined BEFORE /videos/{video_id}
# FastAPI matches routes in order; if {video_id} comes first, "trending" is treated as an ID.
@router.get("/videos/trending", response_model=list[VideoResponse])
async def get_trending(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video)
        .options(selectinload(Video.stats))
        .join(VideoStats, Video.id == VideoStats.video_id)
        .order_by(VideoStats.likes.desc(), VideoStats.views.desc(), Video.created_at.desc())
        .limit(20)
    )
    return result.scalars().all()


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video).options(selectinload(Video.stats)).where(Video.id == video_id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
```

- [ ] **Step 9: Write main.py**

Create `services/video-service/app/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import engine, Base
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 10: Write Dockerfile**

Create `services/video-service/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

- [ ] **Step 11: Run unit tests**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/video-service
pytest tests/ -v
```

Expected: 3 tests pass.

- [ ] **Step 12: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git add services/video-service/
git commit -m "feat: add video-service with videos and trending endpoints"
```

---

## Task 4: Event Service

**Files:**
- Create: `services/event-service/app/__init__.py`
- Create: `services/event-service/app/database.py`
- Create: `services/event-service/app/models.py`
- Create: `services/event-service/app/schemas.py`
- Create: `services/event-service/app/routes.py`
- Create: `services/event-service/app/main.py`
- Create: `services/event-service/tests/__init__.py`
- Create: `services/event-service/tests/test_schemas.py`
- Create: `services/event-service/requirements.txt`
- Create: `services/event-service/Dockerfile`
- Create: `services/event-service/pytest.ini`

- [ ] **Step 1: Write failing schema tests**

Create `services/event-service/tests/__init__.py` (empty).

Create `services/event-service/tests/test_schemas.py`:
```python
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
    # completion_rate and watch_time_seconds are optional
    event = EventCreate(
        user_id="u",
        video_id="v",
        event_type="like",
        idempotency_key="k",
    )
    assert event.completion_rate is None
    assert event.watch_time_seconds is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/event-service
pip install pydantic==2.10.3 pytest==8.3.4
pytest tests/test_schemas.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create requirements.txt, pytest.ini, install**

Create `services/event-service/requirements.txt`:
```
fastapi==0.115.5
uvicorn==0.32.1
sqlalchemy==2.0.36
asyncpg==0.30.0
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
```

Create `services/event-service/pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
```

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: Create app/__init__.py and schemas.py**

Create `services/event-service/app/__init__.py` (empty).

Create `services/event-service/app/schemas.py`:
```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel

EventType = Literal["watch", "like", "skip", "complete", "share", "comment"]


class EventCreate(BaseModel):
    user_id: str
    video_id: str
    event_type: EventType
    completion_rate: float | None = None
    watch_time_seconds: int | None = None
    idempotency_key: str


class EventResponse(BaseModel):
    id: str
    user_id: str
    video_id: str
    event_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Run to verify tests pass**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/event-service
pytest tests/test_schemas.py -v
```

Expected: 4 tests pass.

- [ ] **Step 6: Write database.py**

Create `services/event-service/app/database.py`:
```python
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 7: Write models.py**

Create `services/event-service/app/models.py`:
```python
from datetime import datetime
from sqlalchemy import String, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    video_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    completion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    watch_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

- [ ] **Step 8: Write routes.py**

Create `services/event-service/app/routes.py`:
```python
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database import get_db
from .models import Event
from .schemas import EventCreate, EventResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "event-service", "status": "ok"}


@router.post("/events")
async def create_event(body: EventCreate, db: AsyncSession = Depends(get_db)):
    event = Event(
        id=str(uuid.uuid4()),
        user_id=body.user_id,
        video_id=body.video_id,
        event_type=body.event_type,
        completion_rate=body.completion_rate,
        watch_time_seconds=body.watch_time_seconds,
        idempotency_key=body.idempotency_key,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    try:
        await db.commit()
        return JSONResponse(status_code=201, content={"id": event.id, "status": "created"})
    except IntegrityError:
        await db.rollback()
        return JSONResponse(status_code=200, content={"status": "duplicate_ignored"})


@router.get("/events", response_model=list[EventResponse])
async def list_events(user_id: str | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Event)
    if user_id:
        query = query.where(Event.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()
```

- [ ] **Step 9: Write main.py**

Create `services/event-service/app/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import engine, Base
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 10: Write Dockerfile**

Create `services/event-service/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

- [ ] **Step 11: Run unit tests**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/event-service
pytest tests/ -v
```

Expected: 4 tests pass.

- [ ] **Step 12: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git add services/event-service/
git commit -m "feat: add event-service with idempotency support"
```

---

## Task 5: Ranking Service

**Files:**
- Create: `services/ranking-service/app/__init__.py`
- Create: `services/ranking-service/app/ranking.py`
- Create: `services/ranking-service/app/schemas.py`
- Create: `services/ranking-service/app/clients.py`
- Create: `services/ranking-service/app/routes.py`
- Create: `services/ranking-service/app/main.py`
- Create: `services/ranking-service/tests/__init__.py`
- Create: `services/ranking-service/tests/test_ranking.py`
- Create: `services/ranking-service/requirements.txt`
- Create: `services/ranking-service/Dockerfile`
- Create: `services/ranking-service/pytest.ini`

- [ ] **Step 1: Write failing tests for scoring functions**

Create `services/ranking-service/tests/__init__.py` (empty).

Create `services/ranking-service/tests/test_ranking.py`:
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
    score = compute_freshness(created_at)
    assert score > 0.99


def test_freshness_old_video():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(days=8)
    score = compute_freshness(created_at)
    assert score == 0.0


def test_freshness_midpoint():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(hours=84)  # half of 168h
    score = compute_freshness(created_at)
    assert abs(score - 0.5) < 0.02


def test_popularity_normalized():
    from app.ranking import compute_popularity
    assert abs(compute_popularity(50, 100) - 0.5) < 0.001


def test_popularity_all_zero():
    from app.ranking import compute_popularity
    assert compute_popularity(0, 0) == 0.0


def test_popularity_max():
    from app.ranking import compute_popularity
    assert compute_popularity(100, 100) == 1.0


def test_final_score_all_ones():
    from app.ranking import compute_final_score
    score = compute_final_score(1.0, 1.0, 1.0)
    assert abs(score - 1.0) < 0.001


def test_final_score_interest_only():
    from app.ranking import compute_final_score
    score = compute_final_score(1.0, 0.0, 0.0)
    assert abs(score - 0.60) < 0.001


def test_final_score_freshness_only():
    from app.ranking import compute_final_score
    score = compute_final_score(0.0, 1.0, 0.0)
    assert abs(score - 0.25) < 0.001


def test_final_score_popularity_only():
    from app.ranking import compute_final_score
    score = compute_final_score(0.0, 0.0, 1.0)
    assert abs(score - 0.15) < 0.001
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/ranking-service
pip install pydantic==2.10.3 pytest==8.3.4
pytest tests/test_ranking.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create requirements.txt, pytest.ini, install**

Create `services/ranking-service/requirements.txt`:
```
fastapi==0.115.5
uvicorn==0.32.1
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
```

Create `services/ranking-service/pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
```

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: Create app/__init__.py and ranking.py**

Create `services/ranking-service/app/__init__.py` (empty).

Create `services/ranking-service/app/ranking.py`:
```python
from datetime import datetime, timezone


def compute_interest_match(video_tags: list[str], user_interests: list[dict]) -> float:
    """0.0–1.0: weighted fraction of video tags matched by user interest scores."""
    if not video_tags or not user_interests:
        return 0.0
    interest_map = {i["tag"]: i["score"] for i in user_interests}
    matched = sum(interest_map.get(tag, 0.0) for tag in video_tags)
    return min(1.0, matched / len(video_tags))


def compute_freshness(created_at: datetime) -> float:
    """0.0–1.0: linear decay — 1.0 when brand new, 0.0 at 7 days (168h) old."""
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = (now - created_at).total_seconds() / 3600
    return max(0.0, 1.0 - age_hours / 168.0)


def compute_popularity(likes: int, max_likes: int) -> float:
    """0.0–1.0: likes normalized across the candidate set."""
    if max_likes == 0:
        return 0.0
    return min(1.0, likes / max_likes)


def compute_final_score(interest_match: float, freshness: float, popularity: float) -> float:
    """Weighted combination: 0.60 interest + 0.25 freshness + 0.15 popularity."""
    return round(0.60 * interest_match + 0.25 * freshness + 0.15 * popularity, 4)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/ranking-service
pytest tests/test_ranking.py -v
```

Expected: 14 tests pass.

- [ ] **Step 6: Write schemas.py**

Create `services/ranking-service/app/schemas.py`:
```python
from pydantic import BaseModel


class RankRequest(BaseModel):
    user_id: str
    candidate_video_ids: list[str]


class RankItem(BaseModel):
    video_id: str
    score: float
    reason: str
```

- [ ] **Step 7: Write clients.py**

Create `services/ranking-service/app/clients.py`:
```python
import os
import httpx

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://user-service:8001")
VIDEO_SERVICE_URL = os.environ.get("VIDEO_SERVICE_URL", "http://video-service:8002")


async def get_user_interests(user_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.get(f"{USER_SERVICE_URL}/users/{user_id}/interests")
        response.raise_for_status()
        return response.json()


async def get_video(video_id: str) -> dict | None:
    """Returns video data dict or None if the fetch fails for any reason."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{VIDEO_SERVICE_URL}/videos/{video_id}")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, httpx.TimeoutException):
        return None
```

- [ ] **Step 8: Write routes.py**

Create `services/ranking-service/app/routes.py`:
```python
from datetime import datetime, timezone
from fastapi import APIRouter
from . import clients
from .schemas import RankRequest, RankItem
from .ranking import (
    compute_interest_match,
    compute_freshness,
    compute_popularity,
    compute_final_score,
)

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "ranking-service", "status": "ok"}


@router.post("/rank", response_model=list[RankItem])
async def rank_videos(body: RankRequest) -> list[RankItem]:
    # Fetch user interests — degrade gracefully if unavailable
    try:
        user_interests = await clients.get_user_interests(body.user_id)
    except Exception:
        user_interests = []

    # Fetch candidate videos — skip any that fail individually
    videos = []
    for video_id in body.candidate_video_ids:
        video = await clients.get_video(video_id)
        if video is not None:
            videos.append(video)

    if not videos:
        return []

    max_likes = max(v.get("stats", {}).get("likes", 0) for v in videos)

    results = []
    for video in videos:
        stats = video.get("stats", {})
        tags = video.get("tags", [])
        created_at_str = video.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(timezone.utc)

        interest = compute_interest_match(tags, user_interests)
        freshness = compute_freshness(created_at)
        popularity = compute_popularity(stats.get("likes", 0), max_likes)
        score = compute_final_score(interest, freshness, popularity)

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

- [ ] **Step 9: Write main.py**

Create `services/ranking-service/app/main.py`:
```python
from fastapi import FastAPI
from .routes import router

app = FastAPI()
app.include_router(router)
```

- [ ] **Step 10: Write Dockerfile**

Create `services/ranking-service/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
```

- [ ] **Step 11: Run all unit tests**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/ranking-service
pytest tests/ -v
```

Expected: 14 tests pass.

- [ ] **Step 12: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git add services/ranking-service/
git commit -m "feat: add ranking-service with deterministic scoring formula"
```

---

## Task 6: Feed Service

**Files:**
- Create: `services/feed-service/app/__init__.py`
- Create: `services/feed-service/app/schemas.py`
- Create: `services/feed-service/app/clients.py`
- Create: `services/feed-service/app/routes.py`
- Create: `services/feed-service/app/main.py`
- Create: `services/feed-service/tests/__init__.py`
- Create: `services/feed-service/tests/test_routes.py`
- Create: `services/feed-service/requirements.txt`
- Create: `services/feed-service/Dockerfile`
- Create: `services/feed-service/pytest.ini`

- [ ] **Step 1: Write failing tests for feed routes**

Create `services/feed-service/tests/__init__.py` (empty).

Create `services/feed-service/tests/test_routes.py`:
```python
import pytest
import httpx
from starlette.testclient import TestClient
from app.main import app  # import at module level so app.clients is cached before monkeypatching

TRENDING = [
    {
        "id": "v1",
        "title": "AI Video",
        "creator_id": "u1",
        "tags": ["ai"],
        "duration_seconds": 60,
        "created_at": "2026-01-01T00:00:00",
        "stats": {"views": 10, "likes": 5, "skips": 0, "completion_rate": 0.8},
    }
]
RANKED = [{"video_id": "v1", "score": 0.91, "reason": "matched user interest tags: ai"}]


def test_feed_returns_personalized_when_ranking_succeeds(monkeypatch):
    async def mock_get_trending():
        return TRENDING

    async def mock_rank(user_id, video_ids):
        return RANKED

    monkeypatch.setattr("app.clients.get_trending_videos", mock_get_trending)
    monkeypatch.setattr("app.clients.rank_videos", mock_rank)

    with TestClient(app) as client:
        response = client.get("/feed/user-123")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "personalized_ranking"
    assert data["user_id"] == "user-123"
    assert data["items"][0]["video_id"] == "v1"
    assert data["items"][0]["score"] == 0.91


def test_feed_falls_back_when_ranking_fails(monkeypatch):
    async def mock_get_trending():
        return TRENDING

    async def mock_rank_fails(user_id, video_ids):
        raise httpx.ConnectError("ranking service down")

    monkeypatch.setattr("app.clients.get_trending_videos", mock_get_trending)
    monkeypatch.setattr("app.clients.rank_videos", mock_rank_fails)

    with TestClient(app) as client:
        response = client.get("/feed/user-123")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "trending_fallback"
    assert data["items"][0]["score"] == 0.0
    assert data["items"][0]["reason"] == "trending_fallback"
    assert data["items"][0]["video_id"] == "v1"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/feed-service
pip install fastapi==0.115.5 httpx==0.28.1 pydantic==2.10.3 pytest==8.3.4 starlette
pytest tests/test_routes.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create requirements.txt, pytest.ini, install**

Create `services/feed-service/requirements.txt`:
```
fastapi==0.115.5
uvicorn==0.32.1
pydantic==2.10.3
httpx==0.28.1
pytest==8.3.4
```

Create `services/feed-service/pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
```

```bash
pip install -r requirements.txt
```

- [ ] **Step 4: Create app/__init__.py and schemas.py**

Create `services/feed-service/app/__init__.py` (empty).

Create `services/feed-service/app/schemas.py`:
```python
from pydantic import BaseModel


class FeedItem(BaseModel):
    video_id: str
    score: float
    reason: str


class FeedResponse(BaseModel):
    user_id: str
    source: str
    items: list[FeedItem]
```

- [ ] **Step 5: Write clients.py**

Create `services/feed-service/app/clients.py`:
```python
import os
import httpx

VIDEO_SERVICE_URL = os.environ.get("VIDEO_SERVICE_URL", "http://video-service:8002")
RANKING_SERVICE_URL = os.environ.get("RANKING_SERVICE_URL", "http://ranking-service:8004")


async def get_trending_videos() -> list[dict]:
    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.get(f"{VIDEO_SERVICE_URL}/videos/trending")
        response.raise_for_status()
        return response.json()


async def rank_videos(user_id: str, video_ids: list[str]) -> list[dict]:
    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.post(
            f"{RANKING_SERVICE_URL}/rank",
            json={"user_id": user_id, "candidate_video_ids": video_ids},
        )
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 6: Write routes.py**

Create `services/feed-service/app/routes.py`:
```python
import httpx
from fastapi import APIRouter
from . import clients
from .schemas import FeedItem, FeedResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "feed-service", "status": "ok"}


@router.get("/feed/{user_id}", response_model=FeedResponse)
async def get_feed(user_id: str) -> FeedResponse:
    trending = await clients.get_trending_videos()
    candidate_ids = [v["id"] for v in trending]

    try:
        ranked = await clients.rank_videos(user_id, candidate_ids)
        items = [
            FeedItem(video_id=r["video_id"], score=r["score"], reason=r["reason"])
            for r in ranked
        ]
        return FeedResponse(user_id=user_id, source="personalized_ranking", items=items)
    except Exception:
        # Graceful degradation: return trending videos with default scores
        items = [
            FeedItem(video_id=v["id"], score=0.0, reason="trending_fallback")
            for v in trending
        ]
        return FeedResponse(user_id=user_id, source="trending_fallback", items=items)
```

- [ ] **Step 7: Write main.py**

Create `services/feed-service/app/main.py`:
```python
from fastapi import FastAPI
from .routes import router

app = FastAPI()
app.include_router(router)
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices/services/feed-service
pytest tests/test_routes.py -v
```

Expected: 2 tests pass.

- [ ] **Step 9: Write Dockerfile**

Create `services/feed-service/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
```

- [ ] **Step 10: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git add services/feed-service/
git commit -m "feat: add feed-service with graceful degradation fallback"
```

---

## Task 7: Docker Compose Orchestration

**Files:**
- Create: `infra/docker-compose.yml`

- [ ] **Step 1: Write docker-compose.yml**

Create `infra/docker-compose.yml`:
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
      - "5433:5432"
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
      - "5434:5432"
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
      - "5435:5432"
    volumes:
      - event-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U feedflow -d events"]
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

  event-service:
    build:
      context: ../services/event-service
    ports:
      - "8003:8003"
    environment:
      DATABASE_URL: postgresql+asyncpg://feedflow:feedflow@event-db:5432/events
    depends_on:
      event-db:
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

volumes:
  user-db-data:
  video-db-data:
  event-db-data:
```

- [ ] **Step 2: Build and start all services**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
docker compose -f infra/docker-compose.yml up --build -d
```

Wait ~30 seconds for all containers to start.

- [ ] **Step 3: Verify all health endpoints**

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health
```

Expected for each:
```json
{"service": "<name>", "status": "ok"}
```

If any service fails, check its logs: `docker compose -f infra/docker-compose.yml logs <service-name>`

- [ ] **Step 4: Smoke test the feed flow manually**

```bash
# Create a user
USER=$(curl -s -X POST http://localhost:8001/users \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","display_name":"Test"}')
echo $USER
USER_ID=$(echo $USER | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Seed an interest
curl -s -X POST http://localhost:8001/users/$USER_ID/interests \
  -H "Content-Type: application/json" \
  -d '{"tag":"ai","score":0.9}'

# Create a video
curl -s -X POST http://localhost:8002/videos \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"Intro to AI\",\"creator_id\":\"$USER_ID\",\"tags\":[\"ai\",\"backend\"],\"duration_seconds\":90}"

# Get feed
curl -s http://localhost:8005/feed/$USER_ID | python3 -m json.tool
```

Expected: feed response with `source: "personalized_ranking"` and at least one item.

- [ ] **Step 5: Stop services**

```bash
docker compose -f infra/docker-compose.yml down
```

- [ ] **Step 6: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git add infra/
git commit -m "feat: add docker-compose orchestration for all services and databases"
```

---

## Task 8: Integration Tests

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_service_health.py`
- Create: `tests/integration/test_feed_flow.py`

- [ ] **Step 1: Write conftest.py**

Create `tests/integration/__init__.py` (empty).

Create `tests/integration/conftest.py`:
```python
import httpx
import pytest


def pytest_collection_modifyitems(items):
    """Skip all integration tests if Docker Compose services are not running."""
    try:
        httpx.get("http://localhost:8001/health", timeout=2.0)
    except Exception:
        for item in items:
            item.add_marker(
                pytest.mark.skip(reason="Docker Compose services not running — run: docker compose -f infra/docker-compose.yml up -d")
            )
```

- [ ] **Step 2: Write test_service_health.py**

Create `tests/integration/test_service_health.py`:
```python
import httpx

SERVICES = {
    "user-service": "http://localhost:8001",
    "video-service": "http://localhost:8002",
    "event-service": "http://localhost:8003",
    "ranking-service": "http://localhost:8004",
    "feed-service": "http://localhost:8005",
}


def test_all_services_healthy():
    for name, base_url in SERVICES.items():
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        assert response.status_code == 200, f"{name} returned {response.status_code}"
        data = response.json()
        assert data["status"] == "ok", f"{name} status was {data.get('status')}"
```

- [ ] **Step 3: Write test_feed_flow.py**

Create `tests/integration/test_feed_flow.py`:
```python
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
    # Create user
    user_resp = httpx.post(
        f"{USER_SERVICE}/users",
        json={"email": f"feed-integ-{uuid.uuid4()}@example.com", "display_name": "Feed Tester"},
        timeout=5.0,
    )
    assert user_resp.status_code == 201
    user_id = user_resp.json()["id"]

    # Seed interest
    interest_resp = httpx.post(
        f"{USER_SERVICE}/users/{user_id}/interests",
        json={"tag": "ai", "score": 0.9},
        timeout=5.0,
    )
    assert interest_resp.status_code == 201

    # Create video matching the interest
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

    # Get feed
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
```

- [ ] **Step 4: Start Docker Compose and run integration tests**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
docker compose -f infra/docker-compose.yml up -d
# Wait ~30 seconds for services to be ready
sleep 30
pytest tests/integration/ -v
```

Expected output:
```
tests/integration/test_service_health.py::test_all_services_healthy PASSED
tests/integration/test_feed_flow.py::test_create_user_and_video_appears_in_trending PASSED
tests/integration/test_feed_flow.py::test_feed_returns_ranked_items_for_user PASSED
tests/integration/test_feed_flow.py::test_event_idempotency PASSED
```

If any test fails, check service logs: `docker compose -f infra/docker-compose.yml logs <service-name>`

- [ ] **Step 5: Stop Docker Compose**

```bash
docker compose -f infra/docker-compose.yml down
```

- [ ] **Step 6: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git add tests/
git commit -m "test: add integration tests for health, feed flow, and event idempotency"
```

---

## Task 9: Documentation and Shared Reference Files

**Files:**
- Update: `README.md`
- Create: `shared/schemas/common.py`
- Create: `shared/schemas/events.py`
- Create: `shared/schemas/feed.py`
- Create: `shared/logging/logger.py`
- Create: `shared/config/settings.py`

- [ ] **Step 1: Write shared reference files**

These files are documentation only — no service imports from them.

Create `shared/schemas/common.py`:
```python
# Reference types — not imported by services.
# Each service defines its own equivalent schemas in app/schemas.py.

# VideoItem: { id, title, creator_id, tags, duration_seconds, created_at, stats }
# UserInterest: { tag, score }
# VideoStats: { views, likes, skips, completion_rate }
```

Create `shared/schemas/events.py`:
```python
# Reference: allowed event types used in event-service
# EventType = Literal["watch", "like", "skip", "complete", "share", "comment"]
```

Create `shared/schemas/feed.py`:
```python
# Reference: feed response shape used in feed-service
# FeedResponse: { user_id, source, items: [{ video_id, score, reason }] }
# source values: "personalized_ranking" | "trending_fallback"
```

Create `shared/logging/logger.py`:
```python
# Reference: structured JSON logging pattern for future use
#
# import logging, json
#
# class JSONFormatter(logging.Formatter):
#     def format(self, record):
#         return json.dumps({
#             "level": record.levelname,
#             "message": record.getMessage(),
#             "service": record.__dict__.get("service", "unknown"),
#         })
```

Create `shared/config/settings.py`:
```python
# Reference: env var patterns used across services
#
# Database services:
#   DATABASE_URL — postgresql+asyncpg://user:pass@host:port/db
#
# Ranking service:
#   USER_SERVICE_URL  — http://user-service:8001
#   VIDEO_SERVICE_URL — http://video-service:8002
#
# Feed service:
#   VIDEO_SERVICE_URL    — http://video-service:8002
#   RANKING_SERVICE_URL  — http://ranking-service:8004
```

- [ ] **Step 2: Update README.md with full content**

Overwrite `feedflow-microservices/README.md`:
```markdown
# FeedFlow Microservices

FeedFlow Microservices is the second-generation version of FeedFlow.

The original FeedFlow was a monolithic personalized feed backend (FastAPI + PostgreSQL + Redis + RQ). This version redesigns the system into independently deployable services to improve fault isolation, maintainability, and scalability.

Phase 1 focuses on service decomposition, HTTP-based service communication, Docker Compose orchestration, and integration testing.

## Services

| Service | Port | Responsibility |
|---|---|---|
| user-service | 8001 | Users and interest profiles |
| video-service | 8002 | Video metadata and statistics |
| event-service | 8003 | User interaction events with idempotency |
| ranking-service | 8004 | Rule-based video scoring |
| feed-service | 8005 | Personalized feed API with graceful degradation |

## Architecture

```
Client → Feed Service (8005)
           ├─ GET /videos/trending  → Video Service (8002)
           └─ POST /rank            → Ranking Service (8004)
                                         ├─ GET /users/{id}/interests → User Service (8001)
                                         └─ GET /videos/{id}          → Video Service (8002)

Client → Event Service (8003) → event-db (5435)
Client → User Service (8001)  → user-db  (5433)
Client → Video Service (8002) → video-db (5434)
```

## Run Locally

```bash
docker compose -f infra/docker-compose.yml up --build
```

All services and databases start automatically. Tables are created on first boot.

## Test

**Unit tests** (per service, no infrastructure needed):
```bash
cd services/ranking-service && pytest tests/ -v
cd services/feed-service && pytest tests/ -v
```

**Integration tests** (requires running Docker Compose stack):
```bash
pytest tests/integration/ -v
```

## Key Design Decisions

- **Self-contained services** — each service owns its schemas; no shared library
- **Python uuid.uuid4()** — UUIDs generated in application code, no PostgreSQL extension needed
- **Atomic video creation** — `POST /videos` inserts both `videos` and `video_stats` in one transaction
- **httpx timeout=3.0** — all inter-service calls time out after 3 seconds
- **Ranking partial failures** — if one candidate video fetch fails, it is skipped; the rest are ranked
- **Feed fallback** — if Ranking Service fails, Feed Service returns trending videos with `score=0.0`

## Ranking Formula

```
final_score = 0.60 × interest_match_score
            + 0.25 × freshness_score
            + 0.15 × popularity_score
```

All scores are in [0.0, 1.0].

## Phase 2 (planned)

RabbitMQ message queue, Feature Worker for async interest updates, Redis caching.
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jiaxin/ClaudeProjects/feedflow-microservices
git add shared/ README.md
git commit -m "docs: add README and shared reference schemas"
```
