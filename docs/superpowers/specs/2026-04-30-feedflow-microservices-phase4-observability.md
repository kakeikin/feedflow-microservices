# FeedFlow Microservices — Phase 4 Observability Design

## Goal

Add production-style observability into FeedFlow Microservices: service health, request latency, cache behavior, event publishing, and worker reliability. Every service exposes a `/metrics` endpoint that Prometheus scrapes every 15 seconds. Grafana auto-loads an 11-panel dashboard from a provisioned JSON file.

## Architecture

```
Prometheus (port 9090) scrapes every 15s:
  ├── feed-service:8005/metrics
  ├── ranking-service:8004/metrics
  ├── event-service:8003/metrics
  ├── user-service:8001/metrics
  ├── video-service:8002/metrics
  └── feature-worker:9100/metrics   ← small HTTP server, separate port

Grafana (port 3000)
  └── reads from Prometheus datasource (auto-provisioned)
  └── auto-loads FeedFlow dashboard from feedflow.json (auto-provisioned)
```

Each FastAPI service:
- `app/metrics.py` — defines all `Counter` and `Histogram` objects for that service
- `MetricsMiddleware` in `main.py` — auto-tracks `request_total` and `request_latency_seconds` per method, route template, and status code
- `/metrics` sub-app mounted via `prometheus_client.make_asgi_app()`

Feature Worker:
- `app/metrics.py` — defines worker counters and histogram
- `start_http_server(9100)` called only in `if __name__ == "__main__"` path (not during tests)

## Phase 4 Decision: Skip rabbitmq_exporter

Reason: Prioritize application-level metrics and keep infrastructure simple. RabbitMQ queue depth will be monitored through the RabbitMQ Management UI (port 15672). `rabbitmq_exporter` can be added later as an optional enhancement.

## File Structure

```
infra/
  prometheus/
    prometheus.yml
  grafana/
    provisioning/
      datasources/
        datasource.yml
      dashboards/
        dashboard.yml
    dashboards/
      feedflow.json
  docker-compose.yml              ← add prometheus + grafana services

services/
  feed-service/app/
    metrics.py                    ← feed_request_total, latency, cache/fallback counters
    main.py                       ← add MetricsMiddleware + mount /metrics
    routes.py                     ← increment cache_hit/miss/fallback counters

  ranking-service/app/
    metrics.py                    ← ranking_request_total, latency, candidate_count, upstream_error
    main.py                       ← add MetricsMiddleware + mount /metrics
    routes.py                     ← observe candidate_count, increment upstream_error

  event-service/app/
    metrics.py                    ← event_request_total, latency, ingest/duplicate/publish counters
    main.py                       ← add MetricsMiddleware + mount /metrics
    routes.py                     ← increment ingest/duplicate/publish_success/failure

  user-service/app/
    metrics.py                    ← user_request_total, latency
    main.py                       ← add MetricsMiddleware + mount /metrics

  video-service/app/
    metrics.py                    ← video_request_total, latency
    main.py                       ← add MetricsMiddleware + mount /metrics

  feature-worker/app/
    metrics.py                    ← worker processed/failed/retry/dlq + latency
    consumer.py                   ← increment all worker metrics
    main.py                       ← start_metrics_server() only in __main__ path
```

## MetricsMiddleware (identical shape across all 5 FastAPI services)

Four guardrails are required in every service:

1. Skip `/metrics` and `/metrics/` — use `startswith("/metrics")` so Prometheus scrape requests are never counted in `request_total` or `latency`.
2. Record metrics even when a route raises an exception — use `try/finally` so status defaults to `500`. Do NOT catch the exception inside middleware; let it propagate to FastAPI's exception handler unchanged.
3. Use route template, not raw path — avoids high-cardinality labels. `scope["route"]` is read after `call_next` so routing is complete. Test must verify label is `/users/{user_id}`, not `/users/123`.
4. Status code label is a string — `str(status_code)`.

```python
import time
from starlette.middleware.base import BaseHTTPMiddleware

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
            REQUEST_TOTAL.labels(
                request.method, path, str(status_code)
            ).inc()
            LATENCY.labels(
                request.method, path
            ).observe(time.time() - start)
```

Note: `scope["route"]` is read inside `finally` (after `call_next`) so routing has fully resolved and the route template is available. If `scope["route"]` is `None` (e.g. 404), `request.url.path` is used as fallback — this is acceptable since 404 paths have no template.

`/metrics` is mounted as a sub-application:
```python
from prometheus_client import make_asgi_app
app.mount("/metrics", make_asgi_app())
```

**Design note:** `MetricsMiddleware` is intentionally implemented per service to preserve service independence and avoid introducing a shared runtime package, consistent with the Phase 1 no-shared-library decision.

## Metrics per Service

### feed-service (`app/metrics.py`)

```python
feed_request_total            Counter(labels=[method, route, status])
feed_request_latency_seconds  Histogram(labels=[method, route])
feed_cache_hit_total          Counter
feed_cache_miss_total         Counter
feed_fallback_total           Counter
```

`feed_cache_hit_total` and `feed_cache_miss_total` are incremented in `routes.py` at the cache-aside decision point. `feed_fallback_total` is incremented in the `except` block that triggers the trending fallback.

### ranking-service (`app/metrics.py`)

```python
ranking_request_total            Counter(labels=[method, route, status])
ranking_request_latency_seconds  Histogram(labels=[method, route])
ranking_candidate_count          Histogram(buckets=[1, 5, 10, 20, 50, 100, 200])
ranking_upstream_error_total     Counter
```

`ranking_candidate_count` is observed after the candidate video list is resolved. `ranking_upstream_error_total` is incremented when a video or user-service fetch fails.

### event-service (`app/metrics.py`)

```python
event_request_total            Counter(labels=[method, route, status])
event_request_latency_seconds  Histogram(labels=[method, route])
event_ingest_total             Counter
event_duplicate_total          Counter
event_publish_success_total    Counter
event_publish_failure_total    Counter
```

`event_ingest_total` is incremented on every new event accepted. `event_duplicate_total` is incremented when an idempotency key is already known. `event_publish_success_total` / `event_publish_failure_total` are incremented inside the background publish task.

**Testing note:** Because publish runs in a `BackgroundTask`, the counter may not have incremented by the time `TestClient` returns. Test by extracting the publish logic into a standalone async function (`publish_event_and_record_metrics(...)`) and calling it directly in unit tests, bypassing the BackgroundTask timing.

### user-service (`app/metrics.py`)

```python
user_request_total            Counter(labels=[method, route, status])
user_request_latency_seconds  Histogram(labels=[method, route])
```

### video-service (`app/metrics.py`)

```python
video_request_total            Counter(labels=[method, route, status])
video_request_latency_seconds  Histogram(labels=[method, route])
```

### feature-worker (`app/metrics.py`)

```python
worker_message_processed_total    Counter
worker_message_failed_total       Counter
worker_retry_total                Counter
worker_dlq_total                  Counter
worker_processing_latency_seconds Histogram
```

**Counter semantics (must be implemented exactly):**
- `worker_message_processed_total` — increments only after the full message is successfully processed and ACKed. Never increments for failed messages.
- `worker_message_failed_total` — increments for non-retryable failures only (4xx from upstream, or failure after max retries exhausted). Does not increment on transient failures that are retried.
- `worker_retry_total` — increments each time a message is republished for retry (before max retries reached).
- `worker_dlq_total` — increments when a message is routed to the DLQ (after max retries exhausted).

A single message can contribute to at most one of: `processed_total` OR (`failed_total` + `dlq_total`). It may contribute to multiple increments of `retry_total` before reaching either outcome.

All counters are incremented in `consumer.py`. The latency histogram wraps the full message processing time (from message receipt to ack/nack).

Feature Worker metrics server:

```python
# main.py
from prometheus_client import start_http_server

def start_metrics_server() -> None:
    start_http_server(9100)

if __name__ == "__main__":
    start_metrics_server()
    asyncio.run(main())
```

`start_metrics_server()` is never called during tests — consumer tests import `consumer.py` directly without going through `__main__`.

## Infrastructure Configuration

### `infra/prometheus/prometheus.yml`

`metrics_path: /metrics` is written explicitly in every job for clarity, even though it is the Prometheus default.

Volume path is relative to `infra/docker-compose.yml` location: `./prometheus/prometheus.yml` maps to `infra/prometheus/prometheus.yml`. Do not use `./infra/prometheus/...`.

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

### `infra/grafana/provisioning/datasources/datasource.yml`

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
```

### `infra/grafana/provisioning/dashboards/dashboard.yml`

```yaml
apiVersion: 1
providers:
  - name: FeedFlow
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

### Docker Compose additions

Volume paths are relative to `infra/docker-compose.yml`. `feature-worker` uses `expose` (not `ports`) so Prometheus can reach port 9100 inside the Docker network without publishing to the host.

```yaml
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
```

`feature-worker` service gets `expose: ["9100"]` added.

## Grafana Dashboard — 11 Panels (`feedflow.json`)

The dashboard is provisioned as a JSON file committed to the repo. All PromQL expressions use `rate()` over a 5-minute window for histograms and 1-minute window for counters. Ratio panels use `clamp_min` to avoid division-by-zero NaN on a fresh stack.

### PromQL reference

**Feed latency p50/p99:**
```promql
histogram_quantile(0.99, sum(rate(feed_request_latency_seconds_bucket[5m])) by (le))
histogram_quantile(0.50, sum(rate(feed_request_latency_seconds_bucket[5m])) by (le))
```

**Cache hit rate (NaN-safe):**
```promql
rate(feed_cache_hit_total[1m])
/
clamp_min(rate(feed_cache_hit_total[1m]) + rate(feed_cache_miss_total[1m]), 0.001)
```

**Ranking latency p50/p99:**
```promql
histogram_quantile(0.99, sum(rate(ranking_request_latency_seconds_bucket[5m])) by (le))
histogram_quantile(0.50, sum(rate(ranking_request_latency_seconds_bucket[5m])) by (le))
```

**Ranking candidate count distribution:**
```promql
histogram_quantile(0.99, sum(rate(ranking_candidate_count_bucket[5m])) by (le))
```

**Event publish failure rate (NaN-safe):**
```promql
rate(event_publish_failure_total[1m])
/
clamp_min(rate(event_publish_success_total[1m]) + rate(event_publish_failure_total[1m]), 0.001)
```

**Worker processing latency p99:**
```promql
histogram_quantile(0.99, sum(rate(worker_processing_latency_seconds_bucket[5m])) by (le))
```

### Panel list

1. **Feed request rate** — `rate(feed_request_total[1m])`
2. **Feed latency p50/p99** — histogram_quantile on `feed_request_latency_seconds_bucket`
3. **Cache hit rate** — rate + clamp_min (NaN-safe)
4. **Feed fallback count/rate** — `rate(feed_fallback_total[1m])`
5. **Ranking latency p50/p99** — histogram_quantile on `ranking_request_latency_seconds_bucket`
6. **Ranking candidate count distribution** — histogram_quantile on `ranking_candidate_count_bucket`
7. **Event ingest rate** — `rate(event_ingest_total[1m])`
8. **Event publish success vs failure** — side-by-side rate of both counters
9. **Event publish failure rate** — rate + clamp_min (NaN-safe); motivates Phase 6 outbox pattern
10. **Worker processed/retry/DLQ counts** — rate of `worker_message_processed_total`, `worker_retry_total`, `worker_dlq_total`
11. **Worker processing latency p99** — histogram_quantile on `worker_processing_latency_seconds_bucket`

## Testing

**Middleware behavior tests (per FastAPI service, `tests/test_metrics.py`):**
- Call a normal route → assert `request_total` counter increments by 1, `latency` histogram count increments by 1
- Call `/metrics` → assert `request_total` does NOT increment (scrape path excluded)
- **Verify route template label**: call `GET /users/{user_id}` with a real user ID → assert the label recorded is `/users/{user_id}`, not `/users/123`. This is the high-cardinality guard test.

**Business metric tests:**
- Feed route: `feed_cache_hit_total` increments on cache hit; `feed_cache_miss_total` on miss; `feed_fallback_total` on ranking failure
- Ranking route: `ranking_candidate_count` histogram observes the correct candidate count
- Event route: `event_ingest_total` / `event_duplicate_total` increment in route handler; `event_publish_success_total` / `event_publish_failure_total` tested by calling the extracted publish function directly (not via BackgroundTask)
- Worker consumer: `worker_message_processed_total` increments on ACK; `worker_retry_total` increments on republish; `worker_dlq_total` increments on DLQ route; `worker_message_failed_total` increments only after max retries exhausted

**Registry isolation:** Prometheus metrics are module-level globals. Tests must not redefine the same metric name — this causes `ValueError: Duplicated timeseries`. Use `REGISTRY.get_sample_value(metric_name, labels)` to read counter values in tests.

**Manual verification (requires running stack):**
- `localhost:9090/targets` — all 6 targets show `UP`
- Trigger events via HTTP, watch Grafana panels update live
- Confirm `/metrics` path is not tracked in any `request_total`
- Confirm cache hit rate panel shows a value (not NaN) immediately after first feed request

## Definition of Done

1. Prometheus and Grafana run in Docker Compose and start automatically.
2. All 5 FastAPI services expose `/metrics` with correct counters and histograms.
3. Feature Worker exposes metrics on port 9100 via `start_http_server`.
4. `localhost:9090/targets` shows all 6 targets UP.
5. Grafana dashboard auto-loads on first boot with all 11 panels showing data (not NaN).
6. Unit tests pass for middleware behavior and all business metrics.
7. `/metrics` endpoint is excluded from `request_total` in all services.
8. Route labels use templates (`/users/{user_id}`) not raw paths — verified by test.
9. Worker counter semantics are correct: `processed` and `failed` are mutually exclusive per message.
