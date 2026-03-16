"""
Monitoring Agent v1 — production FastAPI application.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from apps.monitoring_agent import metrics
from apps.monitoring_agent.api.checks import router as checks_router
from apps.monitoring_agent.api.nagios import router as nagios_router
from apps.monitoring_agent.api.status import router as status_router
from apps.monitoring_agent.api.targets import router as targets_router
from apps.monitoring_agent.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("monitoring_agent_startup", version=settings.service_version)

    # Warm up DB engine
    from apps.monitoring_agent.store.postgres import _get_engine

    _get_engine()

    from packages.shared.heartbeat import start_heartbeat

    start_heartbeat("monitoring-agent")

    yield

    from packages.shared.heartbeat import stop_heartbeat

    await stop_heartbeat()
    logger.info("monitoring_agent_shutdown")


settings = get_settings()

app = FastAPI(
    title="Nexus Monitoring Agent",
    version=settings.service_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    with structlog.contextvars.bound_contextvars(path=request.url.path):
        response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.include_router(targets_router)
app.include_router(checks_router)
app.include_router(status_router)
app.include_router(nagios_router)


@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok", "service": "monitoring-agent", "version": settings.service_version}


@app.get("/readyz", tags=["ops"])
async def readyz():
    """Check DB + agent_registry connectivity."""
    try:
        from apps.monitoring_agent.store.postgres import _get_engine, _session_factory

        _get_engine()
        async with _session_factory() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        return Response(
            content='{"status":"not_ready","reason":"db_unavailable"}',
            status_code=503,
            media_type="application/json",
        )
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.registry_base_url}/healthz")
        if r.status_code != 200:
            raise RuntimeError(f"registry status {r.status_code}")
    except Exception:
        return Response(
            content='{"status":"not_ready","reason":"registry_unavailable"}',
            status_code=503,
            media_type="application/json",
        )
    return {"status": "ready"}


@app.get("/metrics", tags=["ops"])
async def get_metrics():
    return Response(content=metrics.snapshot(), media_type="text/plain")


@app.get("/capabilities", tags=["ops"])
async def capabilities():
    return {
        "checks": ["/healthz", "/readyz", "/capabilities"],
        "discovery": "agent_registry",
        "notifications": "notifications_agent",
        "version": settings.service_version,
    }
