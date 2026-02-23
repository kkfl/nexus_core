from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.automation_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.automation_agent.store.database import get_db

router = APIRouter(prefix="/v1/dlq", tags=["dlq"])


@router.post("/{run_id}/replay")
async def replay_dlq_run(
    run_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    """
    (Admin Only) Re-queues a failed run from the DLQ.
    MVP implementation just resets status to pending and increments retry count.
    """
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    from datetime import datetime

    from sqlalchemy import select

    from apps.automation_agent.models import AutomationDLQ, AutomationRun

    stmt = select(AutomationRun).join(AutomationDLQ).where(AutomationRun.id == run_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="DLQ entry not found for run")

    # Reset run status
    run.status = "pending"
    run.error_summary = None

    # Update DLQ
    if run.dlq_entry:
        run.dlq_entry.replay_count += 1
        run.dlq_entry.last_replay_at = datetime.now(UTC)

    # We could optionally clean up old step runs, or let the worker overwrite them
    # For MVP, worker sets them to "running" and overwrites output on subsequent attempts.

    from apps.automation_agent.audit.log import write_audit_event

    await write_audit_event(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        action="replay_dlq",
        result="success",
        tenant_id=run.tenant_id,
        env=run.env,
        automation_id=run.automation_id,
        run_id=run.id,
    )

    await db.commit()
    return {"status": "requeued", "run_id": run.id}
