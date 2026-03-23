"""
PostgreSQL CRUD operations for pbx_agent.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.models import PbxAuditEvent, PbxJob, PbxJobResult, PbxTarget
from apps.pbx_agent.schemas import JobCreate, PbxTargetCreate, PbxTargetUpdate


def _now():
    return datetime.now(UTC)


# ─── Targets ────────────────────────────────────────────────────────────────


async def create_target(db: AsyncSession, payload: PbxTargetCreate) -> PbxTarget:
    target = PbxTarget(
        id=str(uuid.uuid4()),
        tenant_id=payload.tenant_id,
        env=payload.env,
        name=payload.name,
        host=payload.host,
        ami_port=payload.ami_port,
        ami_username=payload.ami_username,
        ami_secret_alias=payload.ami_secret_alias,
        ssh_port=payload.ssh_port,
        ssh_username=payload.ssh_username,
        ssh_key_alias=payload.ssh_key_alias,
        ssh_password_alias=payload.ssh_password_alias,
        status=payload.status,
        metadata_=payload.metadata,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(target)
    await db.flush()
    return target


async def get_target(
    db: AsyncSession, target_id: str, tenant_id: str, env: str
) -> PbxTarget | None:
    stmt = select(PbxTarget).where(
        PbxTarget.id == target_id,
        PbxTarget.tenant_id == tenant_id,
        PbxTarget.env == env,
    )
    r = await db.execute(stmt)
    return r.scalar_one_or_none()


async def get_target_by_id(db: AsyncSession, target_id: str) -> PbxTarget | None:
    """Look up a target by UUID only (tenant/env not required)."""
    stmt = select(PbxTarget).where(PbxTarget.id == target_id)
    r = await db.execute(stmt)
    return r.scalar_one_or_none()


async def list_targets(
    db: AsyncSession, tenant_id: str, env: str, limit: int = 100
) -> list[PbxTarget]:
    stmt = (
        select(PbxTarget)
        .where(
            PbxTarget.tenant_id == tenant_id,
            PbxTarget.env == env,
        )
        .order_by(PbxTarget.name)
        .limit(limit)
    )
    r = await db.execute(stmt)
    return list(r.scalars().all())


async def update_target(
    db: AsyncSession, target_id: str, tenant_id: str, env: str, payload: PbxTargetUpdate
) -> PbxTarget | None:
    target = await get_target(db, target_id, tenant_id, env)
    if not target:
        return None
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k == "metadata":
            target.metadata_ = v
        else:
            setattr(target, k, v)
    target.updated_at = _now()
    await db.flush()
    return target


async def delete_target(db: AsyncSession, target_id: str, tenant_id: str, env: str) -> bool:
    """Delete a PBX target. Returns True if deleted, False if not found."""
    target = await get_target(db, target_id, tenant_id, env)
    if not target:
        return False
    await db.delete(target)
    await db.flush()
    return True


# ─── Jobs ───────────────────────────────────────────────────────────────────


async def create_job(db: AsyncSession, payload: JobCreate) -> PbxJob:
    job = PbxJob(
        id=str(uuid.uuid4()),
        tenant_id=payload.tenant_id,
        env=payload.env,
        pbx_target_id=payload.pbx_target_id,
        action=payload.action,
        payload_redacted={},
        status="pending",
        attempts=0,
        max_attempts=3,
        correlation_id=payload.correlation_id or str(uuid.uuid4()),
        created_at=_now(),
    )
    db.add(job)
    await db.flush()
    return job


async def get_job(db: AsyncSession, job_id: str, tenant_id: str) -> PbxJob | None:
    stmt = select(PbxJob).where(
        PbxJob.id == job_id,
        PbxJob.tenant_id == tenant_id,
    )
    r = await db.execute(stmt)
    return r.scalar_one_or_none()


async def get_job_result(db: AsyncSession, job_id: str) -> PbxJobResult | None:
    stmt = select(PbxJobResult).where(PbxJobResult.job_id == job_id)
    r = await db.execute(stmt)
    return r.scalar_one_or_none()


async def claim_pending_jobs(db: AsyncSession, limit: int = 5) -> list[PbxJob]:
    """Claim up to `limit` pending jobs by setting status=running."""
    stmt = (
        select(PbxJob)
        .where(PbxJob.status == "pending")
        .order_by(PbxJob.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    r = await db.execute(stmt)
    jobs = list(r.scalars().all())
    for job in jobs:
        job.status = "running"
        job.attempts += 1
    await db.flush()
    return jobs


async def complete_job(
    db: AsyncSession,
    job: PbxJob,
    output_summary: dict,
    duration_ms: int,
) -> None:
    job.status = "succeeded"
    result = PbxJobResult(
        job_id=job.id,
        output_summary=output_summary,
        error_redacted=None,
        duration_ms=duration_ms,
        completed_at=_now(),
    )
    db.add(result)
    await db.flush()


async def fail_job(
    db: AsyncSession,
    job: PbxJob,
    error: str,
    duration_ms: int,
) -> None:
    if job.attempts >= job.max_attempts:
        job.status = "failed"
    else:
        job.status = "pending"  # re-queue

    result = PbxJobResult(
        job_id=job.id,
        output_summary=None,
        error_redacted=error[:1000],
        duration_ms=duration_ms,
        completed_at=_now(),
    )
    db.add(result)
    await db.flush()


# ─── Audit ────────────────────────────────────────────────────────────────


async def list_audit(
    db: AsyncSession, tenant_id: str, env: str | None, limit: int = 100
) -> list[PbxAuditEvent]:
    stmt = select(PbxAuditEvent).where(PbxAuditEvent.tenant_id == tenant_id)
    if env:
        stmt = stmt.where(PbxAuditEvent.env == env)
    stmt = stmt.order_by(PbxAuditEvent.created_at.desc()).limit(limit)
    r = await db.execute(stmt)
    return list(r.scalars().all())
