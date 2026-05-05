# FeedFlow Microservices — Phase 2: Event-Driven Feature Pipeline Design

## Overview

Phase 2 extends the Phase 1 microservices architecture with an asynchronous event-driven pipeline. When a user interaction event is ingested, the Event Service publishes it to RabbitMQ. A new Feature Worker service consumes the event and updates user interest scores and video statistics by calling the domain-owning services (User Service and Video Service) via HTTP.

**New repository work:** all changes are in `feedflow-microservices/`

**Out of scope for Phase 2:** Redis caching, ML ranking, outbox pattern, idempotent mutations, Kubernetes.

---

## Architecture

```
POST /events
  → Event Service
      1. Validate input
      2. INSERT into event-db
      3. Return 201
      4. BackgroundTask: publish UserInteractionEvent to RabbitMQ
         (only for newly created events — duplicates returning duplicate_ignored
          do NOT publish)

                        exchange: user.events (direct)
                        routing key: user.interaction
                                    ↓
                        queue: feature.update.queue
                                    ↓
                        Feature Worker
                            1. Parse event message
                            2. GET /videos/{video_id} from Video Service
                            3. PATCH /videos/{video_id}/stats (if any delta is non-zero)
                            4. PATCH /users/{user_id}/interests/{tag} × N tags
                            5. ACK

                        On transient failure → retry up to 3 (manual x-retry-count header)
                        After 3 retries → publish to feature.update.dlq, ACK original
                        On non-retryable failure → ACK, log structured error
```

**Service ownership is unchanged.** User Service owns interest score clamping and upsert. Video Service owns completion rate calculation and stat mutation. Feature Worker computes deltas only and calls domain APIs.

---

## Publishing — Fire-and-Forget via BackgroundTask

Event Service publishes to RabbitMQ in a FastAPI `BackgroundTask` after returning 201.

**Only newly created events are published.** Duplicate submissions that return `duplicate_ignored` must not enqueue a message. The BackgroundTask is only added when the event is freshly inserted (`status: "created"`).

**Delivery risk (accepted in Phase 2):** If the Event Service process crashes after returning 201 but before the BackgroundTask executes, the event is persisted in `event-db` but not delivered to the Feature Worker. This window is accepted to keep the ingestion path low-latency and simple.

**Mitigation:** `event-db` acts as a durable event log. A future outbox publisher can replay unprocessed events from this table. The `idempotency_key` on each event prevents re-ingestion duplicates.

**Phase 3+ upgrade path:** Outbox pattern — atomically write event + pending outbox row in the same transaction; a separate poller publishes from the outbox for at-least-once guarantees.

If publish fails inside the BackgroundTask: log error with `event_id` and `idempotency_key`. Do not fail the original request or retry the publish.

---

## RabbitMQ Topology

| Component | Name | Type | Properties |
|---|---|---|---|
| Exchange | `user.events` | direct | durable |
| Queue | `feature.update.queue` | — | durable, bound to `user.events` with routing key `user.interaction` |
| DLQ | `feature.update.dlq` | — | durable |

**Message format** (JSON):
```json
{
  "event_id": "uuid",
  "user_id": "uuid",
  "video_id": "uuid",
  "event_type": "like",
  "completion_rate": null,
  "watch_time_seconds": null
}
```

---

## New API Endpoints

### User Service — `PATCH /users/{user_id}/interests/{tag}`

**Request:**
```json
{ "delta": 0.1 }
```
`delta` is a signed float. Positive values increase interest; negative values decrease it.

**Behavior:**
- If `(user_id, tag)` exists: `new_score = clamp(old_score + delta, 0.0, 1.0)`
- If `(user_id, tag)` does not exist and `delta > 0`: create row with `score = clamp(delta, 0.0, 1.0)`
- If `(user_id, tag)` does not exist and `delta <= 0`: do not create a row; return `{ "tag": "...", "score": 0.0 }` without writing anything

This keeps `user_interests` clean — a `skip` event does not create a zero-score row for a tag the user has never engaged with positively.

Update for existing rows is atomic using PostgreSQL upsert (`ON CONFLICT DO UPDATE`).

**Response (200):**
```json
{ "tag": "ai", "score": 0.72 }
```

**Error cases:**
- `404` if `user_id` does not exist

---

### Video Service — `PATCH /videos/{video_id}/stats`

**Request:**
```json
{
  "views_delta": 1,
  "likes_delta": 0,
  "skips_delta": 0,
  "completion_rate_sample": null
}
```
All delta fields default to 0. `completion_rate_sample` is a float in `[0.0, 1.0]` or null.

**Behavior:**
- `views = views + views_delta` (atomic SQL update)
- `likes = likes + likes_delta`
- `skips = skips + skips_delta`
- If `completion_rate_sample` is non-null:
  ```
  new_completion_rate = (old_completion_rate * old_views + completion_rate_sample)
                        / (old_views + 1)
  ```
  This formula uses `old_views` (pre-increment) as the denominator, so the new sample is weighted among all complete events seen so far. `views_delta` is applied in the same SQL statement but the completion rate calculation uses the pre-update view count.
- Update is a single atomic SQL statement.

**Response (200):**
```json
{ "views": 42, "likes": 10, "skips": 3, "completion_rate": 0.81 }
```

**Error cases:**
- `404` if `video_id` does not exist

---

## Feature Worker — Event → Delta Mapping

`watch` is a weak engagement signal and does not increment `views`. `complete` represents a counted view with a quality signal and increments `views`. This ensures `views` reflects completed watches rather than double-counting with `watch` events.

| event_type | views_delta | likes_delta | skips_delta | completion_rate_sample | interest delta (per tag) |
|---|---|---|---|---|---|
| `watch` | 0 | 0 | 0 | null | +0.02 |
| `like` | 0 | +1 | 0 | null | +0.10 |
| `skip` | 0 | 0 | +1 | null | −0.08 |
| `complete` | +1 | 0 | 0 | `event.completion_rate` | +0.06 |
| `share` | 0 | 0 | 0 | null | +0.08 |
| `comment` | 0 | 0 | 0 | null | +0.04 |

`watch`, `share`, and `comment` carry no video stat updates in Phase 2 (all deltas are zero). Interest deltas still apply for all event types if the video's tags are known.

When all stat deltas are zero and `completion_rate_sample` is null, the Feature Worker skips the `PATCH /videos/{video_id}/stats` call entirely.

---

## Feature Worker — Processing Flow

For each consumed message:

1. Parse JSON payload into event fields.
2. Call `GET {VIDEO_SERVICE_URL}/videos/{video_id}`:
   - **404 → non-retryable.** ACK the message, log `{"action": "skip", "reason": "video_not_found", "event_id": "..."}`. Stop processing. No stats or interest updates.
   - **5xx or timeout → transient failure.** See retry logic below.
   - **200 → extract `tags` and `stats`.**
3. Look up delta row by `event_type`. If `event_type` is unknown → non-retryable, ACK and log.
4. If any of `views_delta`, `likes_delta`, `skips_delta` is non-zero, or `completion_rate_sample` is non-null:
   - Call `PATCH {VIDEO_SERVICE_URL}/videos/{video_id}/stats`.
5. For each tag in `video.tags`:
   - Call `PATCH {USER_SERVICE_URL}/users/{user_id}/interests/{tag}` with `{"delta": <interest_delta>}`.
   - **404 on user → non-retryable.** ACK, log, stop remaining interest patches.
6. ACK the message.

---

## Retry and Error Handling

### Retryable failures (transient)
- RabbitMQ connection error
- HTTP timeout (any upstream service)
- HTTP 5xx from User Service or Video Service

### Non-retryable failures
- Invalid event schema / unknown `event_type`
- Video not found (404 from Video Service)
- User not found (404 from User Service)
- Any other 4xx

### Retry mechanism — manual `x-retry-count` header

On transient failure:
1. Read `x-retry-count` from message headers (default: 0).
2. If `x-retry-count < 3`:
   - Republish to exchange `user.events` with routing key `user.interaction` and header `x-retry-count = old_count + 1`.
   - ACK the original message.
3. If `x-retry-count >= 3`:
   - Publish the exhausted message directly to `feature.update.dlq`.
   - ACK the original message.

Publishing to the exchange (rather than directly to the queue) keeps the retry path consistent with the normal publish path. DLQ receives messages directly for simplicity in Phase 2.

This approach gives explicit, testable retry counting without relying on `x-death` header semantics, which vary with broker configuration.

**DLQ handling in Phase 2:** Log DLQ arrivals. No auto-replay. Manual replay is possible by re-publishing from DLQ.

### Idempotency caveat (Phase 3)

Phase 2 provides at-least-once message delivery at the queue level, but feature mutations are not fully idempotent. A worker crash after step 4 (video stats patched) but before step 5 (interest patches) completes will cause step 4 to execute twice on retry. Given the small magnitude of deltas, this is accepted in Phase 2.

Phase 3 can add a `processed_events` table keyed on `event_id` to track which mutations have been applied, enabling idempotent retries.

---

## Docker Compose Changes

Add to `infra/docker-compose.yml`:

```yaml
rabbitmq:
  image: rabbitmq:3.13-management-alpine
  ports:
    - "5672:5672"    # AMQP
    - "15672:15672"  # Management UI
  environment:
    RABBITMQ_DEFAULT_USER: feedflow
    RABBITMQ_DEFAULT_PASS: feedflow
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5

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
```

Add healthchecks to `user-service` and `video-service` in `docker-compose.yml` so the `service_healthy` condition is satisfied:

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:800X/health || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
```

Event Service gets a new env var:
```yaml
RABBITMQ_URL: amqp://feedflow:feedflow@rabbitmq:5672/
```

---

## Per-Service File Structure

### Event Service changes
```
services/event-service/app/
  publisher.py      # aio-pika connection + publish_event(); called by BackgroundTask
  routes.py         # add BackgroundTask(publish_event, event) only on status "created"
```

### User Service changes
```
services/user-service/app/
  routes.py         # add PATCH /users/{user_id}/interests/{tag}
  schemas.py        # add InterestDelta schema { delta: float }
```

### Video Service changes
```
services/video-service/app/
  routes.py         # add PATCH /videos/{video_id}/stats
  schemas.py        # add StatsDelta { views_delta, likes_delta, skips_delta, completion_rate_sample }
                    #     StatsResponse { views, likes, skips, completion_rate }
```

### New: Feature Worker
```
services/feature-worker/
  app/
    main.py         # connect to RabbitMQ, declare topology, start consuming
    consumer.py     # message handler: parse → lookup → compute deltas → call APIs → ack/retry
    clients.py      # httpx calls to User Service and Video Service
    mapping.py      # event_type → EventDelta(views_delta, likes_delta, skips_delta,
                    #                          use_completion_rate, interest_delta)
  Dockerfile
  requirements.txt
```

---

## Tech Stack Additions

| Component | Technology |
|---|---|
| Message broker | RabbitMQ 3.13 (management-alpine image) |
| AMQP client | `aio-pika` (async, consistent with existing asyncio services) |
| Worker runtime | Python asyncio loop (no HTTP server) |

---

## Testing

### Unit tests (per service, no infrastructure)

| Service | What to test |
|---|---|
| event-service | `publisher.py`: mock aio-pika channel, assert message body shape and routing key; `routes.py`: assert BackgroundTask is added only for `status: "created"`, not for `duplicate_ignored` |
| feature-worker | `mapping.py`: all 6 event types produce correct `EventDelta` structs; `consumer.py`: mock httpx clients, assert correct PATCH calls per event type; assert video-not-found ACKs without retrying; assert retry counter increments on 5xx; assert exhausted message routes to DLQ |
| user-service | `PATCH` endpoint: delta applied and clamped at 0.0 and 1.0; negative delta on missing tag returns score=0.0 without inserting row; positive delta on missing tag creates row |
| video-service | `PATCH` endpoint: stat deltas applied correctly; completion rate formula uses pre-increment views |

### Integration tests (root-level, Docker Compose running)

`tests/integration/test_feature_pipeline.py`:

All integration tests that assert on downstream state must **poll** rather than use a fixed sleep, to avoid flaky results from variable pipeline latency:

```python
def poll_until(condition_fn, timeout=5.0, interval=0.25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False
```

Tests:
- Create user + video with known tags → post `like` event → poll until user interest score for those tags increases → assert score increased
- Post `watch` event → poll until stats fetched → assert `views` unchanged (watch does not increment views)
- Post `complete` event with `completion_rate=0.8` → poll until `views` incremented by 1 and `completion_rate` updated
- Post two identical `idempotency_key` events → assert second returns `duplicate_ignored` → poll for 2s → assert Feature Worker processed exactly one (interest score incremented once, not twice)

---

## Port Reference (Phase 2 additions)

| Service | Port |
|---|---|
| rabbitmq (AMQP) | 5672 |
| rabbitmq (Management UI) | 15672 |
| feature-worker | none (consumer only) |

---

## Definition of Done

Phase 2 is complete when:

1. RabbitMQ starts as a Docker Compose service with `user.events` exchange, `feature.update.queue`, and `feature.update.dlq` declared on startup
2. `POST /events` returns 201 and enqueues a BackgroundTask that publishes to RabbitMQ; duplicate submissions do not publish
3. Feature Worker consumes events and calls `PATCH /videos/{video_id}/stats` and `PATCH /users/{user_id}/interests/{tag}` per the delta mapping
4. Non-retryable failures (404, unknown event type, schema errors) are ACKed with structured log output, not retried
5. Transient failures retry up to 3 times via `x-retry-count` header; exhausted messages route to `feature.update.dlq`
6. Integration test: post `like` event → user interest score increases for video's tags (polled assertion)
7. Integration test: post `complete` event → video views increment and completion rate updates (polled assertion)
8. Integration test: post `watch` event → video views do not increment
9. All Phase 1 integration tests still pass

---

## Out of Scope for Phase 2

Outbox pattern, Redis caching, idempotent mutations via `processed_events` table, ML ranking, Prometheus metrics, authentication, Kubernetes.
