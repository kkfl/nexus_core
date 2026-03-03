"""Server Agent API -- servers (CRUD, power actions, console, sync)."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.server_agent.adapters.factory import get_adapter
from apps.server_agent.client.vault_client import ServerVaultClient
from apps.server_agent.models import ServerAuditEvent, ServerChangeJob, ServerHost, ServerInstance
from apps.server_agent.schemas import (
    ConsoleOut,
    CreateServerRequest,
    JobCreateResponse,
    ServerOut,
)
from apps.server_agent.store.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/servers", tags=["servers"])


async def _create_job(
    db: AsyncSession,
    tenant_id: str,
    env: str,
    operation: str,
    payload: dict,
    instance_id: str | None = None,
    service_id: str = "server-agent",
    correlation_id: str | None = None,
) -> ServerChangeJob:
    """Create a change job and return it."""
    job = ServerChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        env=env,
        instance_id=instance_id,
        operation=operation,
        payload=payload,
        status="pending",
        created_by_service_id=service_id,
        correlation_id=correlation_id or str(uuid.uuid4()),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _audit(
    db: AsyncSession,
    correlation_id: str,
    tenant_id: str,
    env: str,
    action: str,
    result: str,
    instance_label: str = "",
    provider: str = "",
    reason: str = "",
):
    event = ServerAuditEvent(
        id=str(uuid.uuid4()),
        correlation_id=correlation_id,
        service_id="server-agent",
        tenant_id=tenant_id,
        env=env,
        action=action,
        instance_label=instance_label,
        provider=provider,
        result=result,
        reason=reason,
    )
    db.add(event)
    await db.commit()


# ---------------------------------------------------------------------------
# Server CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ServerOut])
async def list_servers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServerInstance).order_by(ServerInstance.created_at.desc()))
    return result.scalars().all()


@router.get("/{server_id}", response_model=ServerOut)
async def get_server(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    return server


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_server(body: CreateServerRequest, db: AsyncSession = Depends(get_db)):
    host = await db.get(ServerHost, body.host_id)
    if not host:
        raise HTTPException(404, "Host not found")

    job = await _create_job(
        db,
        tenant_id=host.tenant_id,
        env=host.env,
        operation="create_instance",
        payload=body.model_dump(),
    )
    logger.info("server_create_queued", job_id=job.id, host_id=body.host_id, label=body.label)
    return JobCreateResponse(job_id=job.id)


@router.delete("/{server_id}", response_model=JobCreateResponse, status_code=202)
async def delete_server(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")

    job = await _create_job(
        db,
        tenant_id=server.tenant_id,
        env=server.env,
        operation="delete_instance",
        payload={"server_id": server_id, "provider_instance_id": server.provider_instance_id},
        instance_id=server_id,
    )
    logger.info("server_delete_queued", job_id=job.id, server_id=server_id)
    return JobCreateResponse(job_id=job.id)


# ---------------------------------------------------------------------------
# Power actions
# ---------------------------------------------------------------------------


@router.post("/{server_id}/start", response_model=JobCreateResponse, status_code=202)
async def start_server(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    job = await _create_job(
        db,
        server.tenant_id,
        server.env,
        "start",
        {"server_id": server_id, "provider_instance_id": server.provider_instance_id},
        instance_id=server_id,
    )
    return JobCreateResponse(job_id=job.id)


@router.post("/{server_id}/stop", response_model=JobCreateResponse, status_code=202)
async def stop_server(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    job = await _create_job(
        db,
        server.tenant_id,
        server.env,
        "stop",
        {"server_id": server_id, "provider_instance_id": server.provider_instance_id},
        instance_id=server_id,
    )
    return JobCreateResponse(job_id=job.id)


@router.post("/{server_id}/reboot", response_model=JobCreateResponse, status_code=202)
async def reboot_server(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    job = await _create_job(
        db,
        server.tenant_id,
        server.env,
        "reboot",
        {"server_id": server_id, "provider_instance_id": server.provider_instance_id},
        instance_id=server_id,
    )
    return JobCreateResponse(job_id=job.id)


@router.post("/{server_id}/rebuild", response_model=JobCreateResponse, status_code=202)
async def rebuild_server(server_id: str, os_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    job = await _create_job(
        db,
        server.tenant_id,
        server.env,
        "rebuild",
        {
            "server_id": server_id,
            "provider_instance_id": server.provider_instance_id,
            "os_id": os_id,
        },
        instance_id=server_id,
    )
    return JobCreateResponse(job_id=job.id)


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------


@router.get("/{server_id}/console", response_model=ConsoleOut)
async def get_console(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")

    host = await db.get(ServerHost, server.host_id)
    if not host:
        raise HTTPException(500, "Host configuration not found")

    try:
        vault = ServerVaultClient()
        secret = await vault.get_secret(
            alias=host.secret_alias,
            tenant_id=host.tenant_id,
            env=host.env,
            reason="console_access",
        )
        adapter = await get_adapter(host.provider, host.config, secret)
        console = await adapter.get_console_url(server.provider_instance_id)

        # Audit the console access
        await _audit(
            db,
            correlation_id=str(uuid.uuid4()),
            tenant_id=server.tenant_id,
            env=server.env,
            action="console_access",
            result="success",
            instance_label=server.label,
            provider=server.provider,
        )

        return ConsoleOut(
            url=console.url,
            type=console.type,
            token=console.token,
            expires_at=console.expires_at,
        )
    except Exception as e:
        logger.error("console_access_failed", server_id=server_id, error=str(e))
        raise HTTPException(502, f"Console access failed: {e}")


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@router.post("/sync", response_model=JobCreateResponse, status_code=202)
async def sync_servers(host_id: str, db: AsyncSession = Depends(get_db)):
    host = await db.get(ServerHost, host_id)
    if not host:
        raise HTTPException(404, "Host not found")
    job = await _create_job(
        db,
        host.tenant_id,
        host.env,
        "sync",
        {"host_id": host_id},
    )
    return JobCreateResponse(job_id=job.id)
