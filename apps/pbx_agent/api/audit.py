"""
Audit API — GET /v1/audit (admin only).
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.store.database import get_db
from apps.pbx_agent.store import postgres
from apps.pbx_agent.auth.identity import get_service_identity, ServiceIdentity
from apps.pbx_agent.schemas import PbxAuditOut

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("", response_model=List[PbxAuditOut])
async def list_audit(
    tenant_id: str = Query(...),
    env: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    if not identity.is_admin and identity.service_id != "nexus":
        raise HTTPException(status_code=403, detail="Admin access required")
    events = await postgres.list_audit(db, tenant_id=tenant_id, env=env, limit=limit)
    return [PbxAuditOut.model_validate(e) for e in events]
