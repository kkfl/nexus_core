from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.automation_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.automation_agent.models import AutomationStepRun
from apps.automation_agent.schemas import AutomationRunOut, AutomationStepRunOut
from apps.automation_agent.store import postgres
from apps.automation_agent.store.database import get_db

router = APIRouter(prefix="/v1/runs", tags=["runs"])


@router.get("", response_model=list[AutomationRunOut])
async def list_runs(
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    limit: int = Query(50, le=500),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    runs = await postgres.list_runs(db, tenant_id=tenant_id, env=env, limit=limit)
    return [AutomationRunOut.model_validate(r) for r in runs]


@router.get("/{run_id}", response_model=AutomationRunOut)
async def get_run(
    run_id: str,
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    run = await postgres.get_run(db, run_id, tenant_id, env)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return AutomationRunOut.model_validate(run)


@router.get("/{run_id}/steps", response_model=list[AutomationStepRunOut])
async def list_run_steps(
    run_id: str,
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    # Verify run ownership
    run = await postgres.get_run(db, run_id, tenant_id, env)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Explicitly query steps — avoid lazy-load in async session
    stmt = (
        select(AutomationStepRun)
        .where(AutomationStepRun.run_id == run_id)
        .order_by(AutomationStepRun.created_at)
    )
    res = await db.execute(stmt)
    steps = res.scalars().all()
    return [AutomationStepRunOut.model_validate(s) for s in steps]
