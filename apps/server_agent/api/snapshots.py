"""Server Agent API -- snapshots."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.server_agent.models import ServerChangeJob, ServerInstance
from apps.server_agent.schemas import JobCreateResponse, SnapshotCreate, SnapshotOut
from apps.server_agent.models import ServerSnapshot
from apps.server_agent.store.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/servers/{server_id}/snapshots", tags=["snapshots"])


@router.get("", response_model=list[SnapshotOut])
async def list_snapshots(server_id: str, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")
    result = await db.execute(
        select(ServerSnapshot)
        .where(ServerSnapshot.instance_id == server_id)
        .order_by(ServerSnapshot.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=JobCreateResponse, status_code=202)
async def create_snapshot(server_id: str, body: SnapshotCreate, db: AsyncSession = Depends(get_db)):
    server = await db.get(ServerInstance, server_id)
    if not server:
        raise HTTPException(404, "Server not found")

    job = ServerChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=server.tenant_id,
        env=server.env,
        instance_id=server_id,
        operation="create_snapshot",
        payload={
            "server_id": server_id,
            "provider_instance_id": server.provider_instance_id,
            "name": body.name,
            "description": body.description,
        },
        status="pending",
        created_by_service_id="server-agent",
        correlation_id=str(uuid.uuid4()),
    )
    db.add(job)
    await db.commit()
    return JobCreateResponse(job_id=job.id)


@router.delete("/{snapshot_id}", response_model=JobCreateResponse, status_code=202)
async def delete_snapshot(server_id: str, snapshot_id: str, db: AsyncSession = Depends(get_db)):
    snap = await db.get(ServerSnapshot, snapshot_id)
    if not snap or snap.instance_id != server_id:
        raise HTTPException(404, "Snapshot not found")

    server = await db.get(ServerInstance, server_id)
    job = ServerChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=server.tenant_id if server else "",
        env=server.env if server else "",
        instance_id=server_id,
        operation="delete_snapshot",
        payload={
            "snapshot_id": snapshot_id,
            "provider_snapshot_id": snap.provider_snapshot_id,
        },
        status="pending",
        created_by_service_id="server-agent",
        correlation_id=str(uuid.uuid4()),
    )
    db.add(job)
    await db.commit()
    return JobCreateResponse(job_id=job.id)


@router.post("/{snapshot_id}/restore", response_model=JobCreateResponse, status_code=202)
async def restore_snapshot(server_id: str, snapshot_id: str, db: AsyncSession = Depends(get_db)):
    snap = await db.get(ServerSnapshot, snapshot_id)
    if not snap or snap.instance_id != server_id:
        raise HTTPException(404, "Snapshot not found")

    server = await db.get(ServerInstance, server_id)
    job = ServerChangeJob(
        id=str(uuid.uuid4()),
        tenant_id=server.tenant_id if server else "",
        env=server.env if server else "",
        instance_id=server_id,
        operation="restore_snapshot",
        payload={
            "server_id": server_id,
            "provider_instance_id": server.provider_instance_id if server else "",
            "snapshot_id": snapshot_id,
            "provider_snapshot_id": snap.provider_snapshot_id,
        },
        status="pending",
        created_by_service_id="server-agent",
        correlation_id=str(uuid.uuid4()),
    )
    db.add(job)
    await db.commit()
    return JobCreateResponse(job_id=job.id)
