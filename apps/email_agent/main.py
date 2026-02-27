"""
email_agent — production FastAPI application.

Port: 8014
Authentication: X-Service-ID + X-Agent-Key
Integration: mx.gsmcall.com (SMTP + IMAP + SSH admin bridge)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response

from apps.email_agent.api.admin import router as admin_router
from apps.email_agent.api.health import router as health_router
from apps.email_agent.api.inbox import router as inbox_router
from apps.email_agent.api.send import router as send_router
from apps.email_agent.config import config

logger = structlog.get_logger(__name__)

_request_count = 0


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("email_agent_startup", port=config.port)
    yield
    logger.info("email_agent_shutdown")


app = FastAPI(
    title="Nexus Email Agent",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if config.enable_docs else None,
    redoc_url="/redoc" if config.enable_docs else None,
    openapi_url="/openapi.json" if config.enable_docs else None,
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(send_router)
app.include_router(inbox_router)
app.include_router(admin_router)
app.include_router(health_router)


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
    return {"status": "ok", "service": "email-agent", "version": "1.0.0"}


@app.get("/readyz", tags=["ops"])
async def readyz():
    try:
        from sqlalchemy import text

        from apps.email_agent.store.database import async_session

        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return Response(
            content='{"status":"not_ready","reason":"db_unavailable"}',
            status_code=503,
        )


@app.get("/metrics", tags=["ops"])
async def metrics():
    return {
        "request_count": _request_count,
        "service": "email-agent",
    }


@app.get("/v1/capabilities", tags=["capabilities"])
async def capabilities():
    return {
        "service": "email-agent",
        "version": "1.0.0",
        "integration": "mx.gsmcall.com",
        "capabilities": [
            "email.send",
            "email.test_send",
            "email.inbox.search",
            "email.message.read",
            "email.message.raw",
            "email.admin.mailbox.list",
            "email.admin.mailbox.create",
            "email.admin.mailbox.password",
            "email.admin.mailbox.disable",
            "email.admin.alias.add",
            "email.health",
        ],
    }
