"""
Notifications Agent v1 — production FastAPI application.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from apps.notifications_agent import metrics
from apps.notifications_agent.api.audit import router as audit_router
from apps.notifications_agent.api.notify import router as notify_router
from apps.notifications_agent.api.routing_rules import router as routing_router
from apps.notifications_agent.api.templates import router as templates_router
from apps.notifications_agent.config import get_settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("notifications_agent_startup", version=settings.service_version)
    # Warm up DB engine
    from apps.notifications_agent.store.postgres import _get_engine

    _get_engine()
    yield
    logger.info("notifications_agent_shutdown")


settings = get_settings()

app = FastAPI(
    title="Nexus Notifications Agent",
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


# Register routers
app.include_router(notify_router)
app.include_router(templates_router)
app.include_router(routing_router)
app.include_router(audit_router)


@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok", "service": "notifications-agent", "version": settings.service_version}


@app.get("/readyz", tags=["ops"])
async def readyz():
    """Check DB + secrets_agent connectivity."""
    try:
        from apps.notifications_agent.store.postgres import _get_engine, _session_factory

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
            r = await client.get(f"{settings.vault_base_url}/healthz")
        if r.status_code != 200:
            raise RuntimeError(f"vault status {r.status_code}")
    except Exception:
        return Response(
            content='{"status":"not_ready","reason":"secrets_agent_unavailable"}',
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
        "channels": ["telegram", "email", "sms", "webhook"],
        "stubs": ["slack", "teams"],
        "templates": list(
            __import__(
                "apps.notifications_agent.templates.engine", fromlist=["BUILTIN_TEMPLATES"]
            ).BUILTIN_TEMPLATES.keys()
        ),
        "version": settings.service_version,
    }
