"""GET /v1/audit — admin only"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from apps.notifications_agent.auth.identity import ServiceIdentity, get_service_identity, require_admin
from apps.notifications_agent.schemas import AuditEventOut
from apps.notifications_agent.store import postgres as store

router = APIRouter(prefix="/v1", tags=["audit"])


@router.get("/audit", response_model=List[AuditEventOut])
async def get_audit(
    tenant_id: str = Query(...),
    limit: int = Query(100, le=500),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    require_admin(identity)
    events = await store.list_audit(db, tenant_id=tenant_id, limit=limit)
    return [AuditEventOut(
        id=str(e.id), correlation_id=e.correlation_id, service_id=e.service_id,
        tenant_id=e.tenant_id, env=e.env, action=e.action,
        job_id=str(e.job_id) if e.job_id else None,
        delivery_id=str(e.delivery_id) if e.delivery_id else None,
        channel=e.channel, result=e.result, detail=e.detail, created_at=e.created_at,
    ) for e in events]
