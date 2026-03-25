import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireModuleAccess, get_effective_permissions
from packages.shared.db import get_db
from packages.shared.models import AuditEvent, User

router = APIRouter()

# Map audit action prefixes → module keys for filtering
_ACTION_MODULE_MAP: dict[str, str] = {
    "agent_": "orchestration",
    "task_": "orchestration",
    "route_": "orchestration",
    "persona_": "personas",
    "kb_": "knowledge_base",
    "entity_": "entities",
    "secret_": "secrets",
    "vault_": "secrets",
    "pbx_": "pbx",
    "monitoring_": "monitoring",
    "storage_": "storage",
    "carrier_": "carrier",
    "email_": "email",
    "dns_": "dns",
    "server_": "servers",
    "integration_": "integrations",
    "service_": "integrations",
    "user_": "users",
    "login_": "users",
    "password_": "users",
    "api_key_": "api_keys",
    "ip_": "ip_allowlist",
    "backup_": "backup",
    "restore_": "backup",
}


def _action_module(action: str) -> str | None:
    """Return the module key for an audit action, or None if generic."""
    for prefix, module in _ACTION_MODULE_MAP.items():
        if action.startswith(prefix):
            return module
    return None


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
    current_user: User = Depends(RequireModuleAccess("audit", "read")),
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
    events = res.scalars().all()

    # For non-admin users, filter out audit entries from modules they can't access
    if current_user.role != "admin":
        perms = get_effective_permissions(current_user)
        filtered = []
        for ev in events:
            mod = _action_module(ev.action)
            if mod is None or perms.get(mod, "none") != "none":
                filtered.append(ev)
        return filtered

    return events

