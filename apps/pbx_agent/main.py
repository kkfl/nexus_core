"""
pbx_agent — production FastAPI application.

Port: 8011
Authentication: X-Service-ID + X-Agent-Key
Integration: AMI (Asterisk Manager Interface)
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response

from apps.pbx_agent.api.audit import router as audit_router
from apps.pbx_agent.api.diagnostics import router as diagnostics_router
from apps.pbx_agent.api.jobs import router as jobs_router
from apps.pbx_agent.api.status import router as status_router
from apps.pbx_agent.api.targets import router as targets_router
from apps.pbx_agent.config import config
from apps.pbx_agent.jobs.runner import run_worker_loop

logger = structlog.get_logger(__name__)

_request_count = 0
_worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _worker_task
    logger.info("pbx_agent_startup", port=config.port, mock=config.pbx_mock)
    from packages.shared.heartbeat import start_heartbeat

    start_heartbeat("pbx-agent")
    _worker_task = asyncio.create_task(
        run_worker_loop(tick_interval=config.job_worker_tick_seconds)
    )
    yield
    if _worker_task:
        _worker_task.cancel()
    from packages.shared.heartbeat import stop_heartbeat

    await stop_heartbeat()
    logger.info("pbx_agent_shutdown")


app = FastAPI(
    title="Nexus PBX Agent",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if config.enable_docs else None,
    redoc_url="/redoc" if config.enable_docs else None,
    openapi_url="/openapi.json" if config.enable_docs else None,
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(targets_router)
app.include_router(diagnostics_router)
app.include_router(status_router)
app.include_router(jobs_router)
app.include_router(audit_router)


# ─── Middleware ───────────────────────────────────────────────────────────────
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count
    _request_count += 1
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


# ─── Health + Metrics ─────────────────────────────────────────────────────────
@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok", "service": "pbx-agent", "version": "3.0.0"}


@app.get("/readyz", tags=["ops"])
async def readyz():
    # Check DB connectivity
    try:
        from sqlalchemy import text

        from apps.pbx_agent.store.database import async_session

        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return Response(content='{"status":"not_ready","reason":"db_unavailable"}', status_code=503)


@app.get("/metrics", tags=["ops"])
async def metrics():
    return {
        "request_count": _request_count,
        "mock_mode": config.pbx_mock,
        "service": "pbx-agent",
    }


@app.get("/v1/capabilities", tags=["capabilities"])
async def capabilities():
    return {
        "service": "pbx-agent",
        "version": "3.0.0",
        "integration": "AMI",
        "capabilities": [
            "diagnostics.ping",
            "diagnostics.ami-check",
            "diagnostics.version",
            "status.peers",
            "status.registrations",
            "status.channels",
            "status.uptime",
            "jobs.reload",
        ],
        "mutating_actions": ["reload"],
        "mock_mode": config.pbx_mock,
    }
