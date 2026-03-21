import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireRole
from packages.shared.db import get_db
from packages.shared.models import AuditEvent

router = APIRouter()


class AuditEventOut(BaseModel):
    id: int
    actor_id: int | None
    actor_type: str | None
    action: str
    target_type: str | None = None
    target_id: int | None = None
    meta_data: dict | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=list[AuditEventOut])
async def read_audit_events(
    actor_type: str | None = None,
    actor_id: int | None = None,
    action: str | None = None,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
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
