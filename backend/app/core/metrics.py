"""Prometheus metrics for the Cortex API."""

from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUESTS_TOTAL = Counter(
    "cortex_requests_total",
    "Total HTTP requests",
    labelnames=("method", "path", "status"),
)
REQUEST_DURATION = Histogram(
    "cortex_request_duration_seconds",
    "Request duration in seconds",
    labelnames=("method", "path"),
)

# Future search metrics
FUTURE_SEARCH_DURATION = Histogram(
    "cortex_future_search_duration_seconds",
    "Future search duration in seconds",
    labelnames=("objective",),
)

# DataHub metrics
DATAHUB_API_DURATION = Histogram(
    "cortex_datahub_api_duration_seconds",
    "DataHub API call duration in seconds",
    labelnames=("operation",),
)
DATAHUB_ERRORS_TOTAL = Counter(
    "cortex_datahub_errors_total",
    "Total DataHub API errors",
    labelnames=("operation",),
)

# Write-back metrics
WRITEBACK_TOTAL = Counter(
    "cortex_writeback_total",
    "Total write-back records",
    labelnames=("target", "status"),
)

# Application metrics
ACTIVE_SCENARIOS = Gauge(
    "cortex_active_scenarios",
    "Number of scenarios currently being simulated",
)
