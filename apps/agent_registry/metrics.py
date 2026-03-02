import time

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Define Metrics
REQUEST_COUNT = Counter(
    "registry_requests_total",
    "Total HTTP requests to Agent Registry",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "registry_request_latency_seconds",
    "HTTP Request Latency in seconds",
    ["method", "endpoint"],
)


async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    method = request.method

    # Basic route extraction to avoid high cardinality
    if request.url.path.startswith("/v1/agents"):
        endpoint = "/v1/agents"
    elif request.url.path.startswith("/v1/deployments"):
        endpoint = "/v1/deployments"
    elif request.url.path.startswith("/v1/capabilities"):
        endpoint = "/v1/capabilities"
    elif request.url.path.startswith("/v1/audit"):
        endpoint = "/v1/audit"
    else:
        endpoint = "other"

    response = None
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        latency = time.time() - start_time
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)


def get_metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
