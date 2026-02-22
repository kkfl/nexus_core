from typing import Any, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import datetime

from packages.shared.db import get_db
from packages.shared.models import AuditEvent
from apps.nexus_api.dependencies import RequireRole

router = APIRouter()

class AuditEventOut(BaseModel):
    id: int
    actor_id: Optional[int]
    actor_type: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    meta_data: Optional[dict]
    created_at: datetime.datetime

    class Config:
        from_attributes = True

@router.get("/", response_model=List[AuditEventOut])
async def read_audit_events(
    actor_type: Optional[str] = None,
    actor_id: Optional[int] = None,
    action: Optional[str] = None,
    since: Optional[datetime.datetime] = None,
    until: Optional[datetime.datetime] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    stmt = select(AuditEvent)
    if actor_type:
        stmt = stmt.where(AuditEvent.actor_type == actor_type)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if since:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until:
        stmt = stmt.where(AuditEvent.created_at <= until)
        
    stmt = stmt.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()
