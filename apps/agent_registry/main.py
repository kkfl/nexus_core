"""
Agent Registry V1 — FastAPI application.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from apps.agent_registry.api import agents, audit, capabilities, deployments
from apps.agent_registry.config import get_settings
from apps.agent_registry.metrics import get_metrics_response, metrics_middleware
from apps.agent_registry.models import Base
from apps.agent_registry.store.postgres import _engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("agent_registry_startup", version="1.0.0")
    try:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        logger.warning("registry_table_create_skipped", error=str(exc))

    from packages.shared.heartbeat import start_heartbeat

    start_heartbeat("agent_registry")

    yield

    from packages.shared.heartbeat import stop_heartbeat

    await stop_heartbeat()
    logger.info("agent_registry_shutdown")


settings = get_settings()

app = FastAPI(
    title="Nexus Agent Registry",
    version="1.0.0",
    description="Central system of record for agent discovery and capabilities.",
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

from starlette.middleware.base import BaseHTTPMiddleware

app.add_middleware(BaseHTTPMiddleware, dispatch=metrics_middleware)

cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    import uuid

    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    start = time.monotonic()

    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
    )

    response: Response = await call_next(request)
    elapsed_ms = round((time.monotonic() - start) * 1000, 1)

    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"

    logger.info(
        "registry_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------


@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok", "service": "agent-registry", "version": "1.0.0"}


@app.get("/readyz", tags=["ops"])
async def readyz():
    if _engine is None:
        return Response(content='{"status":"not_ready","reason":"no database"}', status_code=503)
    try:
        from sqlalchemy import text

        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return Response(content=f'{{"status":"not_ready","reason":"{exc}"}}', status_code=503)


@app.get("/metrics", tags=["ops"])
async def metrics():
    return get_metrics_response()


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(agents.router)
app.include_router(deployments.router)
app.include_router(capabilities.router)
app.include_router(audit.router)
