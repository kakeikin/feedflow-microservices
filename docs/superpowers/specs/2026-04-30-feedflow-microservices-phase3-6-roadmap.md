# FeedFlow Microservices — Phase 3–6 Roadmap

## Recommended Order

```text
Phase 3: Redis Cache + Ranking Enhancement
Phase 4: Observability
Phase 5: ML Ranking System
Phase 6: Reliability Upgrade — Outbox + Idempotency
```

---

## Phase 3 Schema — Redis Cache + Ranking Enhancement

### Goal

Improve feed latency and make Phase 2 feature updates actually affect feed ranking.

### Why This Phase Matters

Phase 2 updates user interests and video stats asynchronously, but Feed Service and Ranking Service still need to use those updated features effectively.

Phase 3 connects the event pipeline to feed quality and performance.

### New Infrastructure

```text
redis
```

### Services Changed

```text
feed-service
ranking-service
video-service optional
user-service optional
```

### Proposed Architecture

```text
GET /feed/{user_id}
  -> Feed Service
      1. check Redis feed:user:{user_id}
      2. cache hit: return cached feed
      3. cache miss: call Video Service /videos/trending
      4. call Ranking Service /rank
      5. store ranked result in Redis with TTL
      6. return feed
```

### Redis Keys

```text
feed:user:{user_id}        personalized feed cache, TTL 5 minutes
feed:trending              global trending feed cache, TTL 2 minutes
video:{video_id}           optional video metadata cache, TTL 10 minutes
rank:features:{user_id}    optional user feature cache, TTL 5 minutes
```

### Cache Pattern

```text
cache-aside
```

### Required Behavior

- Feed Service checks Redis before calling upstream services.
- Cache miss triggers existing ranking flow.
- Ranking results are cached with TTL.
- If Redis is unavailable, Feed Service should bypass cache and still serve results.
- Response should include source metadata:

```json
{
  "source": "cache_hit" | "personalized_ranking" | "trending_fallback"
}
```

### Ranking Enhancement

Current Ranking Service should be upgraded to use:

```text
user interests from User Service
video tags from Video Service
video stats from Video Service
freshness
completion_rate
likes/views/skips
```

Recommended formula:

```text
score =
  0.45 * interest_match_score
+ 0.20 * freshness_score
+ 0.20 * engagement_score
+ 0.15 * completion_quality_score
```

Where:

```text
interest_match_score: weighted overlap between user interest tags and video tags
freshness_score: linear decay over 7 days
engagement_score: normalized likes/views/skips within candidate set
completion_quality_score: video completion_rate in [0,1]
```

### Cache Invalidation Strategy

Phase 3 simple strategy:

```text
TTL-based invalidation only
```

Optional improvement:

```text
Feature Worker deletes feed:user:{user_id} after processing an event.
```

Recommended Phase 3 decision:

```text
Start with TTL only. Add targeted invalidation if time allows.
```

### Testing

Unit tests:

- Redis cache hit path
- Redis cache miss path
- Redis failure fallback
- Ranking formula with updated video stats
- Ranking formula with updated user interests

Integration tests:

- First GET /feed/{user_id}: cache miss
- Second GET /feed/{user_id}: cache hit
- Post like event, wait for worker, ranking score should reflect updated interest/stats

### Definition of Done

Phase 3 is complete when:

1. Redis runs in Docker Compose.
2. Feed Service uses Redis cache-aside for personalized feeds.
3. Feed Service continues working if Redis is unavailable.
4. Ranking Service uses user interests and video stats updated by Phase 2.
5. Integration tests prove cache hit/miss behavior.
6. Integration tests prove events can influence future feed ranking.

---

## Phase 4 Schema — Observability

### Goal

Add production-style visibility into service health, latency, cache behavior, queue behavior, and worker reliability.

### Why This Phase Matters

Most student projects stop at functionality. Observability makes this look like a real production backend.

### New Infrastructure

```text
prometheus
grafana
```

Optional:

```text
rabbitmq_exporter
```

### Services Changed

```text
all FastAPI services
feature-worker
infra/docker-compose.yml
```

### Metrics to Add

Feed Service:

```text
feed_request_total
feed_request_latency_seconds
feed_cache_hit_total
feed_cache_miss_total
feed_fallback_total
```

Ranking Service:

```text
ranking_request_total
ranking_latency_seconds
ranking_candidate_count
ranking_upstream_error_total
```

Event Service:

```text
event_ingest_total
event_duplicate_total
event_publish_success_total
event_publish_failure_total
```

Feature Worker:

```text
worker_message_processed_total
worker_message_failed_total
worker_retry_total
worker_dlq_total
worker_processing_latency_seconds
```

RabbitMQ:

```text
queue_depth
consumer_count
message_publish_rate
message_ack_rate
```

Database / HTTP optional:

```text
upstream_http_latency_seconds
upstream_http_error_total
```

### Implementation Approach

FastAPI services:

- Use `prometheus-client`.
- Expose `/metrics` endpoint.
- Add middleware to measure request count and latency.

Feature Worker:

- Either expose a small metrics HTTP server on a port, or push metrics through a lightweight exporter.
- Simpler Phase 4 approach: run a tiny HTTP server exposing `/metrics` from the worker container.

Prometheus:

- Scrape all service `/metrics` endpoints.
- Scrape RabbitMQ metrics if exporter is configured.

Grafana:

Create dashboard panels for:

- Feed latency
- Cache hit rate
- Ranking latency
- Event ingestion volume
- Worker success/failure/retry counts
- DLQ count
- RabbitMQ queue depth

### Testing

Unit tests:

- Metrics counters increment when endpoints are called.

Integration/manual verification:

- Prometheus targets show UP.
- Grafana dashboard displays live metrics.
- Trigger test events and verify worker metrics increase.

### Definition of Done

Phase 4 is complete when:

1. Prometheus and Grafana run in Docker Compose.
2. FastAPI services expose `/metrics`.
3. Feature Worker exposes worker metrics.
4. Prometheus scrapes all expected targets.
5. Grafana dashboard shows feed latency, cache hit rate, queue depth, retry count, and DLQ count.
6. README includes screenshots or instructions for viewing the dashboard.

---

## Phase 5 Schema — ML Ranking System

### Goal

Upgrade FeedFlow from a rule-based recommendation backend into an ML-powered recommendation system.

### Why This Phase Matters

This is the phase that turns the project into a true ML System project, suitable for ML Platform / Recommendation / AI Backend internships.

### New Components

```text
ml/
  data/
  training/
  evaluation/
  models/

services/model-service/
```

Optional:

```text
feature-store abstraction
```

### High-Level Architecture

```text
Historical events + user interests + video stats
  -> offline feature generation
  -> training dataset
  -> train ranking model
  -> evaluate model
  -> save model artifact
  -> Model Service loads model
  -> Ranking Service calls Model Service for scores
```

### Model Options

Recommended first version:

```text
Logistic Regression or XGBoost-style classifier/ranker
```

If using only standard libraries:

```text
scikit-learn LogisticRegression / RandomForestClassifier
```

Target label examples:

```text
positive: like, complete, share, comment
negative: skip
weak positive: watch
```

### Feature Set

User features:

```text
user_interest_score_for_video_tags
number_of_matching_tags
average_interest_score
```

Video features:

```text
views
likes
skips
completion_rate
freshness_hours
like_rate
skip_rate
```

Interaction features:

```text
interest_match_score
engagement_score
freshness_score
```

### Offline Training Pipeline

Directory:

```text
ml/training/train_ranker.py
```

Responsibilities:

1. Load sample/historical data.
2. Build feature matrix.
3. Train model.
4. Evaluate model.
5. Save artifact.

Artifact:

```text
ml/models/ranker.pkl
```

### Evaluation Metrics

Classification metrics:

```text
AUC
F1
precision
recall
```

Ranking metrics:

```text
Precision@K
Recall@K
NDCG@K
```

Recommended minimum:

```text
Precision@5
NDCG@10
AUC
```

### Model Service

New service:

```text
model-service
```

API:

```http
POST /predict
```

Request:

```json
{
  "user_id": "uuid",
  "candidates": [
    {
      "video_id": "uuid",
      "features": {
        "interest_match_score": 0.8,
        "freshness_score": 0.6,
        "engagement_score": 0.7,
        "completion_rate": 0.9
      }
    }
  ]
}
```

Response:

```json
[
  { "video_id": "uuid", "score": 0.91 }
]
```

Ranking Service changes:

```text
Ranking Service computes features, then calls Model Service for prediction.
If Model Service fails, Ranking Service falls back to rule-based scoring.
```

### Testing

Unit tests:

- Feature generation correctness
- Model prediction shape
- Ranking Service fallback if Model Service is down
- Evaluation metric functions

Integration tests:

- Train model artifact locally
- Start Model Service
- GET /feed/{user_id} uses ML scores
- Model failure falls back to rule-based ranking

### Definition of Done

Phase 5 is complete when:

1. Offline training pipeline exists.
2. Model artifact is generated and versioned locally.
3. Model Service exposes `/predict`.
4. Ranking Service can use ML scores.
5. Ranking Service falls back to rule-based scoring if Model Service fails.
6. Evaluation report includes at least Precision@K or NDCG@K.
7. README explains model features, labels, and evaluation results.

---

## Phase 6 Schema — Reliability Upgrade: Outbox + Idempotency

### Goal

Close the two major reliability gaps documented in Phase 2:

1. Event may be persisted but not published to RabbitMQ.
2. Worker retry may duplicate feature mutations.

### Why This Phase Matters

This phase turns the event pipeline from a functional demo into a reliability-aware distributed system.

### Part A — Outbox Pattern

Current Phase 2 risk:

```text
POST /events returns 201.
Event Service crashes before BackgroundTask publishes.
Event is in event-db but not in RabbitMQ.
```

Outbox solution:

```text
Within the same DB transaction:
  insert event row
  insert outbox row with status = pending

Outbox Publisher:
  polls pending outbox rows
  publishes to RabbitMQ
  marks row as published
```

### New Table

In event-db:

```sql
outbox_events (
  id UUID PRIMARY KEY,
  event_id UUID NOT NULL,
  payload JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  retry_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL,
  published_at TIMESTAMP NULL,
  last_error TEXT NULL
)
```

### New Component

```text
outbox-publisher
```

Responsibilities:

- Poll `outbox_events` where status = pending.
- Publish payload to RabbitMQ.
- Mark as published on success.
- Increment retry_count and record error on failure.

### Event Service Change

Remove BackgroundTask publishing.

New flow:

```text
POST /events
  -> insert event + outbox row atomically
  -> return 201

Outbox Publisher
  -> publish to RabbitMQ asynchronously
```

### Part B — Idempotent Mutations

Current Phase 2 risk:

```text
Feature Worker patches video stats, then crashes.
Message retries.
Video stats may be incremented again.
```

Solution options:

Option 1: Processed events table in Feature Worker database.

Option 2: Domain services accept `event_id` and enforce idempotency.

Recommended Phase 6 choice:

```text
Domain services own idempotency for their own mutations.
```

### User Service Idempotency

Add table:

```sql
processed_interest_events (
  event_id UUID NOT NULL,
  user_id UUID NOT NULL,
  tag TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  PRIMARY KEY (event_id, user_id, tag)
)
```

Modify API:

```http
PATCH /users/{user_id}/interests/{tag}
```

Request:

```json
{
  "event_id": "uuid",
  "delta": 0.1
}
```

Behavior:

```text
If (event_id, user_id, tag) already processed:
  return current score without applying delta again.
Else:
  apply delta and insert processed record in same transaction.
```

### Video Service Idempotency

Add table:

```sql
processed_stat_events (
  event_id UUID PRIMARY KEY,
  video_id UUID NOT NULL,
  created_at TIMESTAMP NOT NULL
)
```

Modify API:

```http
PATCH /videos/{video_id}/stats
```

Request:

```json
{
  "event_id": "uuid",
  "views_delta": 1,
  "likes_delta": 0,
  "skips_delta": 0,
  "completion_rate_sample": 0.8
}
```

Behavior:

```text
If event_id already processed:
  return current stats without applying deltas again.
Else:
  apply stats update and insert processed record in same transaction.
```

### Feature Worker Change

Feature Worker includes `event_id` in all PATCH calls.

### Testing

Integration tests:

- Event insert creates outbox row.
- Outbox Publisher publishes pending events.
- Simulate publish failure, verify retry_count increments.
- Send same RabbitMQ message twice, verify stats update only once.
- Send same RabbitMQ message twice, verify interest delta only applies once.

### Definition of Done

Phase 6 is complete when:

1. Event Service writes event + outbox row atomically.
2. BackgroundTask publishing is removed.
3. Outbox Publisher reliably publishes pending events to RabbitMQ.
4. Domain mutation APIs accept `event_id`.
5. User interest updates are idempotent per event/tag.
6. Video stats updates are idempotent per event.
7. Duplicate worker delivery does not double-increment stats or interests.
8. README documents reliability guarantees and remaining limitations.
