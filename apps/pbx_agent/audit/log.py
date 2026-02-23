"""
Audit event writer for pbx_agent.
"""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.models import PbxAuditEvent

logger = structlog.get_logger(__name__)


async def write_audit_event(
    db: AsyncSession,
    correlation_id: str,
    service_id: str,
    action: str,
    result: str,
    tenant_id: str | None = None,
    env: str | None = None,
    target_id: str | None = None,
    detail: str | None = None,
) -> None:
    event = PbxAuditEvent(
        id=str(uuid.uuid4()),
        correlation_id=correlation_id,
        service_id=service_id,
        tenant_id=tenant_id,
        env=env,
        action=action,
        target_id=target_id,
        result=result,
        detail=detail,
        created_at=datetime.now(UTC),
    )
    db.add(event)
    try:
        await db.flush()
    except Exception as e:
        logger.error("audit_write_failed", error=str(e))
