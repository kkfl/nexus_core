"""
Audit router — GET /v1/audit (admin only)
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.agent_registry.auth.identity import ServiceIdentity, get_service_identity
from apps.agent_registry.models import RegistryAuditEvent
from apps.agent_registry.schemas import AuditEventOut
from apps.agent_registry.store import postgres as store

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("", response_model=List[AuditEventOut])
async def get_audit_events(
    tenant_id: Optional[str] = Query(None),
    env: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> List[AuditEventOut]:
    """Retrieve an audit log of all mutations inside the registry. Admin only."""
    if not identity.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only.")

    stmt = select(RegistryAuditEvent).order_by(RegistryAuditEvent.created_at.desc()).limit(limit)
    if tenant_id:
        stmt = stmt.where(RegistryAuditEvent.tenant_id == tenant_id)
    if env:
        stmt = stmt.where(RegistryAuditEvent.env == env)

    result = await db.execute(stmt)
    return [AuditEventOut.model_validate(e) for e in result.scalars().all()]
