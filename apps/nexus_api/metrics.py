import time
from fastapi import Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Define Metrics
REQUEST_COUNT = Counter(
    "nexus_requests_total",
    "Total HTTP requests to Nexus API",
    ["method", "endpoint", "status_code"]
)

REQUEST_LATENCY = Histogram(
    "nexus_request_latency_seconds",
    "HTTP Request Latency in seconds",
    ["method", "endpoint"]
)

TASK_STATUS_COUNT = Counter(
    "nexus_task_status_total",
    "Total tasks by status",
    ["status", "task_type"]
)

async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    method = request.method
    
    # Very basic route extraction to avoid high cardinality
    if request.url.path.startswith("/api-keys"):
        endpoint = "/api-keys"
    elif request.url.path.startswith("/tasks"):
        endpoint = "/tasks"
    elif request.url.path.startswith("/kb"):
        endpoint = "/kb"
    elif request.url.path.startswith("/auth"):
        endpoint = "/auth"
    elif request.url.path.startswith("/entities"):
        endpoint = "/entities"
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
    # We could query DB for queue depth here and update a Gauge, but keeping it simple
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
