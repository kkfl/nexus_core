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
    ServerResourcesOut,
)
from apps.server_agent.store.postgres import get_db
from packages.shared.alerts import send_alert

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


@router.get("/{server_id}/resources", response_model=ServerResourcesOut)
async def get_server_resources(server_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch live resource usage for an individual server."""
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
            reason="server_resources_check",
        )
        adapter = await get_adapter(host.provider, host.config, secret)
        resources = await adapter.get_instance_resources(server.provider_instance_id)

        return ServerResourcesOut(
            provider=resources.provider,
            status=resources.status,
            cpu_usage_pct=resources.cpu_usage_pct,
            cpu_cores=resources.cpu_cores,
            ram_used_mb=resources.ram_used_mb,
            ram_total_mb=resources.ram_total_mb,
            ram_usage_pct=resources.ram_usage_pct,
            disk_total_gb=resources.disk_total_gb,
            disk_used_gb=resources.disk_used_gb,
            disk_usage_pct=resources.disk_usage_pct,
            bandwidth_in_gb=resources.bandwidth_in_gb,
            bandwidth_out_gb=resources.bandwidth_out_gb,
            uptime_seconds=resources.uptime_seconds,
            # GPU
            gpu_name=resources.gpu_name,
            gpu_usage_pct=resources.gpu_usage_pct,
            gpu_vram_used_mb=resources.gpu_vram_used_mb,
            gpu_vram_total_mb=resources.gpu_vram_total_mb,
            gpu_vram_usage_pct=resources.gpu_vram_usage_pct,
            gpu_temp_c=resources.gpu_temp_c,
            gpu_power_draw_w=resources.gpu_power_draw_w,
            gpu_count=resources.gpu_count,
            # LLM
            llm_model_loaded=resources.llm_model_loaded,
            llm_requests_active=resources.llm_requests_active,
            llm_avg_latency_ms=resources.llm_avg_latency_ms,
            llm_tokens_per_sec=resources.llm_tokens_per_sec,
            # Voice
            voice_concurrent_calls=resources.voice_concurrent_calls,
            voice_max_concurrent=resources.voice_max_concurrent,
            voice_avg_latency_ms=resources.voice_avg_latency_ms,
            voice_total_calls_today=resources.voice_total_calls_today,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("server_resources_failed", server_id=server_id, error=str(e))
        raise HTTPException(502, f"Failed to fetch server resources: {e}")


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
    send_alert("server_create", "server-agent", f"Label: {body.label} (host: {host.label})")
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
    send_alert("server_delete", "server-agent", f"Server: {server.label or server_id}")
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
    send_alert("server_start", "server-agent", f"Server: {server.label or server_id}")
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
    send_alert("server_stop", "server-agent", f"Server: {server.label or server_id}")
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
    send_alert("server_reboot", "server-agent", f"Server: {server.label or server_id}")
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
    send_alert(
        "server_rebuild", "server-agent", f"Server: {server.label or server_id} (OS: {os_id})"
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
    except Exception as e:
        logger.error("console_access_failed", server_id=server_id, error=str(e))
        raise HTTPException(502, f"Console access failed: {e}")

    return ConsoleOut(
        url=console.url,
        type=console.type,
        token=console.token,
        expires_at=console.expires_at,
    )


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@router.post("/sync", status_code=202)
async def sync_servers(host_id: str | None = None, db: AsyncSession = Depends(get_db)):
    if host_id:
        # Sync a single host
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

    # Sync ALL active hosts
    result = await db.execute(select(ServerHost).where(ServerHost.is_active.is_(True)))
    hosts = result.scalars().all()
    if not hosts:
        raise HTTPException(404, "No active hosts registered")

    job_ids = []
    for host in hosts:
        job = await _create_job(
            db,
            host.tenant_id,
            host.env,
            "sync",
            {"host_id": host.id},
        )
        job_ids.append(job.id)
        logger.info("sync_queued", host_id=host.id, provider=host.provider, label=host.label)

    return {
        "job_ids": job_ids,
        "status": "pending",
        "message": f"Sync queued for {len(hosts)} hosts",
    }
