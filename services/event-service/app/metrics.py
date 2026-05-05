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
