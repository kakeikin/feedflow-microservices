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
