"""
Secrets Agent — FastAPI main application.

Registers routes:
  GET  /healthz           liveness check
  GET  /readyz            readiness check (DB connectivity)
  GET  /metrics           basic counters (Prometheus text format)
  /v1/secrets/*           secret lifecycle endpoints
  /v1/policies/*          policy management (admin)
  /v1/audit/*             audit log query (admin)
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from apps.secrets_agent.api import audit, policies, secrets
from apps.secrets_agent.dependencies import _engine
from apps.secrets_agent.models import VaultBase

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Request counters (simple in-memory Prometheus-style metrics for V1)
# ---------------------------------------------------------------------------
_COUNTERS: dict[str, int] = {
    "requests_total": 0,
    "secrets_read_total": 0,
    "auth_denied_total": 0,
}

# ---------------------------------------------------------------------------
# Lifespan (startup/shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("secrets_agent_startup", version="1.0.0")
    # Create vault tables if they don't already exist (Alembic handles migrations)
    # The async_engine is None if DATABASE_URL is missing — safe for tests.
    if _engine is not None:
        try:
            async with _engine.begin() as conn:
                await conn.run_sync(VaultBase.metadata.create_all)
        except Exception as exc:
            logger.warning("vault_table_create_skipped", error=str(exc))
    yield
    logger.info("secrets_agent_shutdown")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

ENABLE_DOCS = os.environ.get("ENABLE_DOCS", "false").lower() == "true"

app = FastAPI(
    title="Nexus Secrets Vault",
    version="1.0.0",
    description="Production-grade Secrets Vault for the Nexus multi-agent platform.",
    redirect_slashes=False,
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)

# CORS — only used when accessed directly; production goes through Caddy
cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Middleware: correlation ID + security headers (no CSP that blocks APIs)
# ---------------------------------------------------------------------------


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    import uuid

    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    start = time.monotonic()
    _COUNTERS["requests_total"] += 1

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
    response.headers["Referrer-Policy"] = "no-referrer"

    logger.info(
        "vault_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        elapsed_ms=elapsed_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Health + metrics
# ---------------------------------------------------------------------------


@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok", "service": "secrets-agent"}


@app.get("/readyz", tags=["ops"])
async def readyz():
    if _engine is None:
        return Response(content='{"status":"not_ready","reason":"no database"}', status_code=503)
    try:
        async with _engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return Response(content=f'{{"status":"not_ready","reason":"{exc}"}}', status_code=503)


@app.get("/metrics", tags=["ops"])
async def metrics():
    lines = [f"vault_{k} {v}" for k, v in _COUNTERS.items()]
    return Response(content="\n".join(lines) + "\n", media_type="text/plain")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(secrets.router)
app.include_router(policies.router)
app.include_router(audit.router)
