"""Server Agent API -- jobs (status + history)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.server_agent.models import ServerChangeJob
from apps.server_agent.schemas import JobOut
from apps.server_agent.store.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
async def list_jobs(
    limit: int = 50,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(ServerChangeJob).order_by(ServerChangeJob.created_at.desc()).limit(limit)
    if status:
        q = q.where(ServerChangeJob.status == status)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(ServerChangeJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job
