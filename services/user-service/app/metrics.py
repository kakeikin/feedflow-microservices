from prometheus_client import Counter, Histogram

USER_REQUEST_TOTAL = Counter(
    "user_request_total",
    "Total user service requests",
    ["method", "route", "status"],
)
USER_REQUEST_LATENCY = Histogram(
    "user_request_latency_seconds",
    "User service request latency in seconds",
    ["method", "route"],
)
