from prometheus_client import Counter, Histogram

RANKING_REQUEST_TOTAL = Counter(
    "ranking_request_total",
    "Total ranking service requests",
    ["method", "route", "status"],
)
RANKING_REQUEST_LATENCY = Histogram(
    "ranking_request_latency_seconds",
    "Ranking service request latency in seconds",
    ["method", "route"],
)
RANKING_CANDIDATE_COUNT = Histogram(
    "ranking_candidate_count",
    "Number of candidate videos resolved for ranking",
    buckets=[1, 5, 10, 20, 50, 100, 200],
)
RANKING_UPSTREAM_ERROR_TOTAL = Counter(
    "ranking_upstream_error_total",
    "Total video fetch failures (get_video returned None)",
)
