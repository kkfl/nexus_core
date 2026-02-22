import uuid
import structlog
from fastapi import FastAPI, Request
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apps.nexus_api.routers import auth, agents, personas, tasks, artifacts, task_routes, persona_defaults, kb, secrets, audit, entities, pbx, internal, monitoring, storage, carrier, docs
from apps.nexus_api.metrics import metrics_middleware, get_metrics_response

logger = structlog.get_logger()

# Docs disabled unless explicitly enabled
ENABLE_DOCS = os.environ.get("ENABLE_DOCS", "false").lower() == "true"
docs_kwargs = {} if ENABLE_DOCS else {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(
    title="Nexus Core API",
    version="1.0.0",
    description="Nexus Core orchestrator and persona registry.",
    **docs_kwargs
)

# CORS
cors_origins = os.environ.get("CORS_ORIGINS", "").split(",")
if not cors_origins or cors_origins == [""]:
    cors_origins = [] # Default deny

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
app.add_middleware(BaseHTTPMiddleware, dispatch=metrics_middleware)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    
    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
    )
    
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    
    # Security Headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    if ENABLE_DOCS:
        response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' data:;"
        
    return response

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(personas.router, prefix="/personas", tags=["personas"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(artifacts.router, prefix="/artifacts", tags=["artifacts"])
app.include_router(task_routes.router, prefix="/task-routes", tags=["task-routes"])
app.include_router(persona_defaults.router, prefix="/persona-defaults", tags=["persona-defaults"])
app.include_router(kb.router, prefix="/kb", tags=["kb"])
app.include_router(secrets.router, prefix="/secrets", tags=["secrets"])
app.include_router(audit.router, prefix="/audit", tags=["audit"])
app.include_router(entities.router, prefix="/entities", tags=["entities"])
app.include_router(pbx.router, prefix="/pbx", tags=["pbx"])
app.include_router(internal.router, prefix="/internal", tags=["internal"])
app.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])
app.include_router(storage.router, prefix="/storage", tags=["storage"])
app.include_router(carrier.router, prefix="/carrier", tags=["carrier"])
app.include_router(docs.router, prefix="/docs", tags=["docs"])

@app.get("/healthz", tags=["health"])
async def healthz():
    return {"status": "ok"}

@app.get("/readyz", tags=["health"])
async def readyz():
    return {"status": "ready"}

@app.get("/metrics", tags=["metrics"])
async def metrics():
    return get_metrics_response()

@app.get("/api/version", tags=["system"])
async def get_version():
    version_str = "unknown"
    version_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "VERSION")
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            version_str = f.read().strip()
    return {
        "version": version_str,
        "commit": os.environ.get("GIT_COMMIT", "unknown"),
        "build_time": os.environ.get("BUILD_TIME", "unknown")
    }
