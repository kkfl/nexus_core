"""
Jobs API — POST /v1/jobs, GET /v1/jobs/{job_id}
Async mutating actions (V1: reload only).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.audit.log import write_audit_event
from apps.pbx_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.pbx_agent.schemas import JobCreate, PbxJobDetailOut, PbxJobOut, PbxJobResultOut
from apps.pbx_agent.store import postgres
from apps.pbx_agent.store.database import get_db

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

ALLOWED_ACTIONS = {"reload"}


@router.post("", response_model=PbxJobOut, status_code=202)
async def create_job(
    payload: JobCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    if identity.read_only:
        raise HTTPException(status_code=403, detail="Read-only service cannot create jobs")
    if payload.action not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Action '{payload.action}' not supported. Allowed: {sorted(ALLOWED_ACTIONS)}",
        )

    # Verify target exists
    target = await postgres.get_target(db, payload.pbx_target_id, payload.tenant_id, payload.env)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    job = await postgres.create_job(db, payload)
    await write_audit_event(
        db,
        identity.correlation_id,
        identity.service_id,
        f"job.{payload.action}",
        "queued",
        tenant_id=payload.tenant_id,
        env=payload.env,
        target_id=target.id,
    )
    await db.commit()
    await db.refresh(job)
    return PbxJobOut.model_validate(job)


@router.get("/{job_id}", response_model=PbxJobDetailOut)
async def get_job(
    job_id: str,
    tenant_id: str = Query(...),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    job = await postgres.get_job(db, job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = await postgres.get_job_result(db, job_id)
    job_out = PbxJobOut.model_validate(job)
    result_out = PbxJobResultOut.model_validate(result) if result else None

    return PbxJobDetailOut(
        **job_out.model_dump(),
        result=result_out,
    )
