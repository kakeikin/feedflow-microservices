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

## Phase 3: Redis Cache + Ranking Enhancement

Phase 3 connects the Phase 2 async feature pipeline to feed quality and performance.

- Added Redis cache-aside pattern to Feed Service. First request is a cache miss and triggers full ranking; subsequent requests return `source=cache_hit` from Redis with a 5-minute TTL. If Redis is unavailable, Feed Service bypasses cache and continues serving results.
- Added `source` metadata to feed responses: `cache_hit` | `personalized_ranking` | `trending_fallback`.
- Upgraded Ranking Service from a 3-factor to a 4-factor scoring formula incorporating `completion_rate` and net engagement (likes − skips):

```
score = 0.45 × interest_match_score
      + 0.20 × freshness_score
      + 0.20 × engagement_score
      + 0.15 × completion_quality_score
```

- Added integration tests proving cache hit on second request and that like + complete events processed by Feature Worker increase a video's ranking score.

## Phase 2: Event-Driven Feature Pipeline

Phase 2 extends FeedFlow with an asynchronous RabbitMQ-based feature pipeline. When the Event Service receives a user interaction, it persists the event and publishes a `UserInteractionEvent` to RabbitMQ in a background task. The Feature Worker consumes the event, fetches video metadata, and updates video statistics and user interest scores through the domain-owning services.

Key engineering decisions:
- Event Service uses fire-and-forget background publishing to keep ingestion latency low.
- User Service owns interest-score clamping and atomic upserts.
- Video Service owns statistics mutation and completion-rate calculation.
- Feature Worker computes deltas only and communicates through HTTP APIs.
- Transient failures are retried up to 3 times before routing messages to a DLQ.
- Phase 2 documents delivery and idempotency caveats, with outbox and processed-event tracking planned for later phases.
