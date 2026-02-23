"""
Audit API — GET /v1/audit (admin only).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.pbx_agent.schemas import PbxAuditOut
from apps.pbx_agent.store import postgres
from apps.pbx_agent.store.database import get_db

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("", response_model=list[PbxAuditOut])
async def list_audit(
    tenant_id: str = Query(...),
    env: str | None = Query(None),
    limit: int = Query(100, le=1000),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    if not identity.is_admin and identity.service_id != "nexus":
        raise HTTPException(status_code=403, detail="Admin access required")
    events = await postgres.list_audit(db, tenant_id=tenant_id, env=env, limit=limit)
    return [PbxAuditOut.model_validate(e) for e in events]
