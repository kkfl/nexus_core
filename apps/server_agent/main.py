"""
Server Agent -- FastAPI main application.

Routes:
  GET  /healthz
  GET  /readyz
  GET  /metrics
  GET  /v1/hosts
  POST /v1/hosts
  DELETE /v1/hosts/{id}
  GET  /v1/servers
  GET  /v1/servers/{id}
  POST /v1/servers
  DELETE /v1/servers/{id}
  POST /v1/servers/{id}/start|stop|reboot|rebuild
  GET  /v1/servers/{id}/console
  POST /v1/servers/sync
  GET  /v1/servers/{id}/snapshots
  POST /v1/servers/{id}/snapshots
  DELETE /v1/servers/{id}/snapshots/{snap_id}
  POST /v1/servers/{id}/snapshots/{snap_id}/restore
  GET  /v1/servers/{id}/backups
  POST /v1/servers/{id}/backups
  POST /v1/servers/{id}/backups/{backup_id}/restore
  GET  /v1/servers/{id}/backups/schedule
  PUT  /v1/servers/{id}/backups/schedule
  DELETE /v1/servers/{id}/backups/schedule
  GET  /v1/jobs
  GET  /v1/jobs/{id}
  GET  /v1/catalog/regions|plans|os
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from apps.server_agent.api import backups, catalog, hosts, jobs, servers, snapshots
from apps.server_agent.config import get_settings
from apps.server_agent.jobs.worker import run_worker_loop
from apps.server_agent.models import ServerBase
from apps.server_agent.store.postgres import _get_engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("server_agent_startup", version="1.0.0")
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(ServerBase.metadata.create_all)
    except Exception as exc:
        logger.warning("server_table_create_skipped", error=str(exc))

    # Start job worker as background task
    worker_task = asyncio.create_task(run_worker_loop())
    logger.info("job_worker_background_task_started")

    yield

    # Cancel worker on shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("server_agent_shutdown")


settings = get_settings()
ENABLE_DOCS = settings.enable_docs

app = FastAPI(
    title="Nexus Server Agent",
    version="1.0.0",
    description="Server lifecycle management for the Nexus multi-agent platform (Vultr + Proxmox).",
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


# ---------------------------------------------------------------------------
# Request middleware
# ---------------------------------------------------------------------------


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
        "server_request",
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
    return {"status": "ok", "service": "server-agent", "version": "1.0.0"}


@app.get("/readyz", tags=["ops"])
async def readyz():
    from apps.server_agent.store.postgres import _engine

    if _engine is None:
        return Response(content='{"status":"not_ready","reason":"no database"}', status_code=503)
    try:
        from sqlalchemy import text

        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return Response(content=f'{{"status":"not_ready","reason":"{exc}"}}', status_code=503)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(hosts.router)
app.include_router(servers.router)
app.include_router(snapshots.router)
app.include_router(backups.router)
app.include_router(jobs.router)
app.include_router(catalog.router)
