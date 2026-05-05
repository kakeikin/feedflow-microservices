from prometheus_client import Counter, Histogram

VIDEO_REQUEST_TOTAL = Counter(
    "video_request_total",
    "Total video service requests",
    ["method", "route", "status"],
)
VIDEO_REQUEST_LATENCY = Histogram(
    "video_request_latency_seconds",
    "Video service request latency in seconds",
    ["method", "route"],
)
