from prometheus_client import Counter, Histogram

WORKER_PROCESSED_TOTAL = Counter(
    "worker_message_processed_total",
    "Total messages successfully processed and ACKed",
)
WORKER_FAILED_TOTAL = Counter(
    "worker_message_failed_total",
    "Total messages that failed non-retryably (DLQ path after max retries)",
)
WORKER_RETRY_TOTAL = Counter(
    "worker_message_retry_total",
    "Total times a message was republished for retry",
)
WORKER_DLQ_TOTAL = Counter(
    "worker_message_dlq_total",
    "Total messages routed to the dead-letter queue",
)
WORKER_LATENCY = Histogram(
    "worker_processing_latency_seconds",
    "Total message processing time from receipt to ack",
)
