"""Audit router — admin-only access to vault audit events."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.secrets_agent.dependencies import ServiceIdentity, get_vault_db, require_admin
from apps.secrets_agent.models import VaultAuditEvent
from apps.secrets_agent.schemas import AuditEventOut

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
async def query_audit(
    service_id: str | None = Query(None),
    tenant_id: str | None = Query(None),
    env: str | None = Query(None),
    secret_alias: str | None = Query(None),
    action: str | None = Query(None),
    result: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: ServiceIdentity = Depends(require_admin),
    db: AsyncSession = Depends(get_vault_db),
) -> list[AuditEventOut]:
    """
    Query vault audit events. Admin only.
    Secret values are NEVER present in audit records — only aliases and metadata.
    """
    q = select(VaultAuditEvent)
    if service_id:
        q = q.where(VaultAuditEvent.service_id == service_id)
    if tenant_id:
        q = q.where(VaultAuditEvent.tenant_id == tenant_id)
    if env:
        q = q.where(VaultAuditEvent.env == env)
    if secret_alias:
        q = q.where(VaultAuditEvent.secret_alias == secret_alias)
    if action:
        q = q.where(VaultAuditEvent.action == action)
    if result:
        q = q.where(VaultAuditEvent.result == result)
    q = q.order_by(VaultAuditEvent.ts.desc()).offset(offset).limit(limit)
    rows = await db.execute(q)
    return [AuditEventOut.model_validate(r) for r in rows.scalars().all()]
