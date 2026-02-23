import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from apps.automation_agent.models import AutomationAuditEvent

logger = structlog.get_logger(__name__)

async def write_audit_event(
    db: AsyncSession,
    correlation_id: str,
    service_id: str,
    action: str,
    result: str,
    tenant_id: Optional[str] = None,
    env: Optional[str] = None,
    automation_id: Optional[str] = None,
    run_id: Optional[str] = None,
    detail: Optional[str] = None
):
    """
    Persist an audit event to the database.
    Does not commit the transaction (caller must commit).
    """
    event = AutomationAuditEvent(
        correlation_id=correlation_id,
        service_id=service_id,
        tenant_id=tenant_id,
        env=env,
        action=action,
        result=result,
        automation_id=automation_id,
        run_id=run_id,
        detail=detail
    )
    db.add(event)
    
    # Also log it for operational visibility
    log_func = logger.info if result == "success" else logger.warning
    log_func(
        "audit_event",
        action=action,
        result=result,
        automation_id=automation_id,
        run_id=run_id
    )
