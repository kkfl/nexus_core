"""Jobs router — GET /v1/jobs/{job_id}, GET /v1/jobs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.dns_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.dns_agent.models import DnsChangeJob
from apps.dns_agent.schemas import JobOut
from apps.dns_agent.store import postgres as store

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> JobOut:
    """Get change job status. Poll this after creating an upsert/delete job."""
    job = await store.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JobOut.model_validate(job)


@router.get("", response_model=list[JobOut])
async def list_jobs(
    tenant_id: str = Query(...),
    env: str = Query(None),
    job_status: str = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> list[JobOut]:
    """List change jobs for a tenant, optionally filtered by status."""
    q = select(DnsChangeJob).where(DnsChangeJob.tenant_id == tenant_id)
    if env:
        q = q.where(DnsChangeJob.env == env)
    if job_status:
        q = q.where(DnsChangeJob.status == job_status)
    q = q.order_by(DnsChangeJob.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return [JobOut.model_validate(j) for j in result.scalars().all()]
