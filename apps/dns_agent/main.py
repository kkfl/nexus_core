"""
DNS Agent — FastAPI main application.

Routes:
  GET  /healthz
  GET  /readyz
  GET  /metrics
  GET  /v1/zones
  POST /v1/zones
  GET  /v1/records
  POST /v1/records/upsert
  POST /v1/records/delete
  POST /v1/sync
  GET  /v1/jobs/{job_id}
  GET  /v1/jobs
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from apps.dns_agent.api import jobs, records, sync, zones
from apps.dns_agent.config import get_settings
from apps.dns_agent.metrics import inc, metrics_text
from apps.dns_agent.models import DnsBase
from apps.dns_agent.store.postgres import _get_engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("dns_agent_startup", version="2.0.0")
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(DnsBase.metadata.create_all)
    except Exception as exc:
        logger.warning("dns_table_create_skipped", error=str(exc))
    yield
    logger.info("dns_agent_shutdown")


settings = get_settings()
ENABLE_DOCS = settings.enable_docs

app = FastAPI(
    title="Nexus DNS Agent",
    version="2.0.0",
    description="Production-grade DNS management for the Nexus multi-agent platform.",
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)

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
    inc("requests_total")

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

    if response.status_code >= 400:
        inc("requests_error_total")

    logger.info(
        "dns_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Health / Ops
# ---------------------------------------------------------------------------

@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok", "service": "dns-agent", "version": "2.0.0"}


@app.get("/readyz", tags=["ops"])
async def readyz():
    from apps.dns_agent.store.postgres import _engine
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
    return Response(content=metrics_text(), media_type="text/plain")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(zones.router)
app.include_router(records.router)
app.include_router(sync.router)
app.include_router(jobs.router)
