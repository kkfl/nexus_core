"""
Carrier Agent v2 — Production Upgrade
Replaces prototype's mock-only provider and old nexus/internal/secrets pattern with:
  - VaultClient for credentials (account_sid + auth_token from secrets_agent)
  - Twilio as the V1 real provider (mock still supported via CARRIER_MOCK=true)
  - structlog structured logging — no credentials ever logged
  - pydantic-settings config
  - Proper lifespan, /healthz, /readyz

Secret aliases (pre-create in secrets_agent):
  carrier.<target_id>.account_sid  — Twilio Account SID
  carrier.<target_id>.auth_token   — Twilio Auth Token

For mock targets, set provider="mock" — no secrets required.
"""

from __future__ import annotations

import datetime
import os
import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from apps.carrier_agent.adapters.factory import get_adapter
from apps.secrets_agent.client.vault_client import VaultClient
from packages.shared.agent_sdk import handle_agent_execute
from packages.shared.schemas.agent_sdk import (
    AgentTaskError,
    AgentTaskRequest,
    AgentTaskResponse,
    JobSummary,
    ProposedWrite,
)

logger = structlog.get_logger(__name__)


from fastapi import Depends

from apps.carrier_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.carrier_agent.config import config as _settings


def _vault_client() -> VaultClient:
    return VaultClient(
        base_url=_settings.vault_base_url,
        service_id=_settings.vault_service_id,
        api_key=_settings.vault_agent_key,
    )


def _safe_error(exc: Exception) -> str:
    msg = re.sub(r"[A-Za-z0-9+/=]{32,}", "[REDACTED]", str(exc))
    return msg[:1000]


async def _fetch_target_metadata(target_id: str) -> dict[str, Any]:
    """Fetch non-credential target metadata from nexus_api."""
    if _settings.carrier_mock and target_id == "mock":
        return {"name": "Mock Provider", "provider": "mock", "id": target_id}
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(
            f"{_settings.nexus_base_url}/internal/carrier/targets/{target_id}",
            headers={"X-Nexus-Internal": _settings.nexus_agent_key},
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch carrier target '{target_id}': HTTP {r.status_code}"
            )
        return r.json()


# ---------------------------------------------------------------------------
# Execution handler
# ---------------------------------------------------------------------------


async def _execute_handler(req: AgentTaskRequest) -> AgentTaskResponse:
    target_id = req.payload.get("carrier_target_id")
    if not target_id:
        return AgentTaskResponse(
            ok=False,
            error=AgentTaskError(code="missing_target", message="carrier_target_id is required"),
        )

    tenant_id = req.payload.get("tenant_id", "nexus")
    env = req.payload.get("env", "prod")
    persona_received = (
        {"name": req.persona.name, "version": req.persona.version} if req.persona else None
    )
    ctx_count = len(req.context) if req.context else 0
    correlation_id = req.payload.get("correlation_id", str(uuid.uuid4()))

    logger.info(
        "carrier_task_start",
        task_type=req.type,
        target_id=target_id,
        correlation_id=correlation_id,
    )

    try:
        target = await _fetch_target_metadata(target_id)
        provider = target.get("provider", "mock" if _settings.carrier_mock else "twilio")

        vault = _vault_client()
        adapter = await get_adapter(
            provider=provider,
            target_id=target_id,
            vault=vault,
            tenant_id=tenant_id,
            env=env,
            correlation_id=correlation_id,
        )

        result_data: dict[str, Any] = {
            "persona_received": persona_received,
            "context_received_count": ctx_count,
            "provider": provider,
        }
        proposed_writes: list[ProposedWrite] = []
        job_summary = None
        now = datetime.datetime.utcnow().isoformat()

        if req.type == "carrier.account.status":
            status = await adapter.get_account_status()
            result_data.update(
                {
                    "status": status.status,
                    "balance": status.balance,
                    "currency": status.currency,
                    "friendly_name": status.friendly_name,
                }
            )

        elif req.type == "carrier.dids.list":
            dids = await adapter.list_dids()
            result_data.update({"dids": [d.__dict__ for d in dids], "total_count": len(dids)})

        elif req.type == "carrier.did.lookup":
            number = req.payload.get("number")
            if not number:
                return AgentTaskResponse(
                    ok=False, error=AgentTaskError(code="missing_number", message="number required")
                )
            did = await adapter.get_did(number)
            if not did:
                return AgentTaskResponse(
                    ok=False,
                    error=AgentTaskError(code="not_found", message=f"DID {number} not found"),
                )
            result_data["did"] = did.__dict__

        elif req.type == "carrier.trunks.list":
            trunks = await adapter.list_trunks()
            result_data["trunks"] = [t.__dict__ for t in trunks]

        elif req.type == "carrier.messaging.status":
            ms = await adapter.get_messaging_status()
            result_data["messaging_status"] = ms.__dict__

        elif req.type == "carrier.cnam.status":
            number = req.payload.get("number")
            cnam = await adapter.get_cnam_status(number=number)
            result_data["cnam_status"] = cnam.__dict__

        elif req.type == "carrier.snapshot.inventory":
            acct = await adapter.get_account_status()
            dids = await adapter.list_dids()
            trunks = await adapter.list_trunks()
            ms = await adapter.get_messaging_status()
            cnam = await adapter.get_cnam_status()

            proposed_writes.append(
                ProposedWrite(
                    entity_kind="carrier_target",
                    external_ref=target_id,
                    action="upsert",
                    patch={
                        "name": target.get("name"),
                        "provider": provider,
                        "status": acct.status,
                        "last_seen_at": now,
                    },
                    idempotency_key=f"carrier_target:{target_id}:{correlation_id}",
                )
            )
            for d in dids:
                proposed_writes.append(
                    ProposedWrite(
                        entity_kind="carrier_did",
                        external_ref=f"{target_id}:{d.number}",
                        action="upsert",
                        patch={k: v for k, v in d.__dict__.items() if not k.startswith("_")},
                        idempotency_key=f"carrier_did:{target_id}:{d.number}:{correlation_id}",
                    )
                )
            for t in trunks:
                proposed_writes.append(
                    ProposedWrite(
                        entity_kind="carrier_trunk",
                        external_ref=f"{target_id}:{t.trunk_id}",
                        action="upsert",
                        patch={k: v for k, v in t.__dict__.items() if not k.startswith("_")},
                        idempotency_key=f"carrier_trunk:{target_id}:{t.trunk_id}:{correlation_id}",
                    )
                )
            job_summary = JobSummary(
                kind="carrier_snapshot",
                status="succeeded",
                details={"dids_count": len(dids), "trunks_count": len(trunks)},
            )
            result_data["snapshot_status"] = "generated"

        else:
            return AgentTaskResponse(
                ok=False,
                error=AgentTaskError(code="unknown_task", message=f"Task {req.type} not supported"),
            )

        return AgentTaskResponse(
            ok=True,
            result=result_data,
            proposed_writes=proposed_writes or None,
            job_summary=job_summary,
        )

    except Exception as exc:
        safe_msg = _safe_error(exc)
        logger.error("carrier_task_failed", task_type=req.type, target_id=target_id, error=safe_msg)
        return AgentTaskResponse(
            ok=False,
            error=AgentTaskError(code="execution_failed", message=safe_msg),
        )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

import asyncio

from apps.carrier_agent.jobs.runner import run_worker_loop

_worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _worker_task
    logger.info("carrier_agent_startup", version="2.0.0")
    from packages.shared.heartbeat import start_heartbeat
    start_heartbeat("carrier-agent")
    _worker_task = asyncio.create_task(run_worker_loop(tick_interval=5))
    yield
    if _worker_task:
        _worker_task.cancel()
    from packages.shared.heartbeat import stop_heartbeat
    await stop_heartbeat()
    logger.info("carrier_agent_shutdown")


app = FastAPI(
    title="Nexus Carrier Agent",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _settings.enable_docs else None,
    redoc_url="/redoc" if _settings.enable_docs else None,
    openapi_url="/openapi.json" if _settings.enable_docs else None,
)

cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=cors_origins or ["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok", "service": "carrier-agent", "version": "2.0.0"}


@app.get("/readyz", tags=["ops"])
async def readyz():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{_settings.vault_base_url}/healthz")
        if r.status_code == 200:
            return {"status": "ready"}
    except Exception:
        pass
    return Response(
        content='{"status":"not_ready","reason":"secrets-agent unavailable"}', status_code=503
    )


@app.post("/execute", response_model=AgentTaskResponse)
async def execute_task(
    req: AgentTaskRequest,
    request: Request,
    identity: ServiceIdentity = Depends(get_service_identity),
):
    return await handle_agent_execute(req, request, _execute_handler)


@app.get("/capabilities")
async def get_capabilities():
    return {
        "capabilities": [
            "carrier.account.status",
            "carrier.dids.list",
            "carrier.did.lookup",
            "carrier.trunks.list",
            "carrier.messaging.status",
            "carrier.cnam.status",
            "carrier.snapshot.inventory",
        ],
        "providers": ["twilio", "mock"],
        "version": "2.0.0",
    }
