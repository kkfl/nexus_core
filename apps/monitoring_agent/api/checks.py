"""
Checks REST API
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.monitoring_agent.engine.checker import run_checks
from apps.monitoring_agent.store.postgres import get_db

router = APIRouter(prefix="/v1/check", tags=["checks"])


@router.post("/run", status_code=status.HTTP_200_OK)
async def trigger_checks(
    tenant_id: str | None = Query(None),
    env: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    import uuid

    correlation_id = str(uuid.uuid4())  # MOCK temporarily until auth added

    results = await run_checks(db, tenant_id, env, correlation_id)
    return {"status": "completed", "correlation_id": correlation_id, "summary": results}
