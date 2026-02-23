"""
Audit Sink — write immutable audit events to vault_audit_events.

INVARIANT: Secret values MUST NEVER be passed to any parameter here.
Only metadata (alias, tenant_id, env, action, result) is recorded.
"""

from __future__ import annotations

import datetime
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.secrets_agent.models import VaultAuditEvent

logger = logging.getLogger(__name__)


async def log_event(
    db: AsyncSession,
    *,
    request_id: str,
    service_id: str,
    tenant_id: str,
    env: str,
    secret_alias: str,
    action: str,
    result: str,  # "allowed" | "denied" | "error"
    reason: str | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Write a vault audit event. Never raises — log failures are caught and
    logged at WARNING level so they don't break the main request path.

    IMPORTANT: Do NOT pass secret values to any parameter here.
               Only aliases and metadata are permitted.
    """
    try:
        event = VaultAuditEvent(
            id=str(uuid.uuid4()),
            request_id=request_id,
            service_id=service_id,
            tenant_id=tenant_id,
            env=env,
            secret_alias=secret_alias,
            action=action,
            result=result,
            reason=reason,
            ip_address=ip_address,
            ts=datetime.datetime.utcnow(),
        )
        db.add(event)
        await db.flush()
        logger.debug(
            "vault_audit",
            extra={
                "request_id": request_id,
                "service_id": service_id,
                "tenant_id": tenant_id,
                "env": env,
                "alias": secret_alias,  # alias only, never value
                "action": action,
                "result": result,
            },
        )
    except Exception as exc:
        # Audit failure should not mask the main operation result,
        # but must be visible in operational logs.
        logger.warning(
            "vault_audit_write_failed",
            extra={"error": str(exc), "action": action, "alias": secret_alias},
        )
