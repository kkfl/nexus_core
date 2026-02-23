from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from apps.automation_agent.store.database import get_db
from apps.automation_agent.auth.identity import get_service_identity, ServiceIdentity
from apps.automation_agent.models import AutomationAuditEvent

router = APIRouter(prefix="/v1/audit", tags=["audit"])

@router.get("")
async def list_audit_events(
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    limit: int = Query(50, le=500),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="Audit log requires admin access")
        
    stmt = select(AutomationAuditEvent).where(
        AutomationAuditEvent.tenant_id == tenant_id,
        AutomationAuditEvent.env == env
    ).order_by(desc(AutomationAuditEvent.created_at)).limit(limit)
    
    res = await db.execute(stmt)
    events = res.scalars().all()
    
    return [
        {
            "id": e.id,
            "correlation_id": e.correlation_id,
            "action": e.action,
            "result": e.result,
            "automation_id": e.automation_id,
            "run_id": e.run_id,
            "created_at": e.created_at.isoformat()
        } for e in events
    ]
