"""Server Agent API -- backups (CRUD, schedule, restore)."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.server_agent.models import ServerBackup, ServerChangeJob, ServerInstance
from apps.server_agent.schemas import (
    BackupOut,
    BackupScheduleOut,
    BackupScheduleRequest,
    JobCreateResponse,
)
from apps.server_agent.store.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/servers/{server_id}/backups", tags=["backups"])


@router.get("", response_model=list[BackupOut])
async def list_backups(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    result = await db.execute(
        select(ServerBackup)
        .where(ServerBackup.instance_id == server_id)
        .order_by(ServerBackup.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_backup(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")

    job = ServerChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=server.tenant_id,
        env=server.env,
        instance_id=server_id,
        operation="create_backup",
        payload={
            "server_id": server_id,
            "provider_instance_id": server.provider_instance_id,
        },
        status="pending",
        created_by_service_id="server-agent",
        correlation_id=str(uuid.uuid4()),
    )
    db.add(job)
    await db.commit()
    return JobCreateResponse(job_id=job.id)


@router.post("/{backup_id}/restore", response_model=JobCreateResponse, status_code=202)
async def restore_backup(
    server_id: str, backup_id: str, db: AsyncSession = Depends(get_db)
):
    backup = await db.get(ServerBackup, backup_id)
    if not backup or backup.instance_id != server_id:
        raise HTTPException(404, "Backup not found")

    server = await db.get(ServerInstance, server_id)
    job = ServerChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=server.tenant_id if server else "",
        env=server.env if server else "",
        instance_id=server_id,
        operation="restore_backup",
        payload={
            "server_id": server_id,
            "provider_instance_id": server.provider_instance_id if server else "",
            "backup_id": backup_id,
            "provider_backup_id": backup.provider_backup_id,
        },
        status="pending",
        created_by_service_id="server-agent",
        correlation_id=str(uuid.uuid4()),
    )
    db.add(job)
    await db.commit()
    return JobCreateResponse(job_id=job.id)


# ---------------------------------------------------------------------------
# Backup schedule
# ---------------------------------------------------------------------------


@router.get("/schedule", response_model=BackupScheduleOut | None)
async def get_backup_schedule(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    # Schedule is stored in host-level config or fetched from provider
    # For now return None (no schedule configured)
    return None


@router.put("/schedule", status_code=200)
async def set_backup_schedule(
    server_id: str, body: BackupScheduleRequest, db: AsyncSession = Depends(get_db)
):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")

    job = ServerChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=server.tenant_id,
        env=server.env,
        instance_id=server_id,
        operation="set_backup_schedule",
        payload={
            "server_id": server_id,
            "provider_instance_id": server.provider_instance_id,
            **body.model_dump(),
        },
        status="pending",
        created_by_service_id="server-agent",
        correlation_id=str(uuid.uuid4()),
    )
    db.add(job)
    await db.commit()
    return JobCreateResponse(job_id=job.id)


@router.delete("/schedule", status_code=202)
async def disable_backups(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")

    job = ServerChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=server.tenant_id,
        env=server.env,
        instance_id=server_id,
        operation="disable_backups",
        payload={
            "server_id": server_id,
            "provider_instance_id": server.provider_instance_id,
        },
        status="pending",
        created_by_service_id="server-agent",
        correlation_id=str(uuid.uuid4()),
    )
    db.add(job)
    await db.commit()
    return JobCreateResponse(job_id=job.id)
