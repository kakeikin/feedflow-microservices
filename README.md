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

## Integration Issues Fixed

During live Docker Compose integration testing, two production-style issues were identified and fixed:

1. Fixed PostgreSQL timezone mismatch by explicitly defining all datetime columns as `DateTime(timezone=True)`, preventing insertion failures when using timezone-aware Python datetimes.

2. Fixed async SQLAlchemy response serialization by re-querying videos with `selectinload(Video.stats)` after commit, preventing `MissingGreenlet` errors caused by lazy loading outside the async session context.

## Phase 2 (planned)

RabbitMQ message queue, Feature Worker for async interest updates, Redis caching.
