from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.automation_agent.audit.log import write_audit_event
from apps.automation_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.automation_agent.schemas import (
    AutomationCreate,
    AutomationOut,
    AutomationRunOut,
    AutomationUpdate,
    TriggerRunRequest,
)
from apps.automation_agent.store import postgres
from apps.automation_agent.store.database import get_db

router = APIRouter(prefix="/v1/automations", tags=["automations"])


@router.post("", response_model=AutomationOut, status_code=status.HTTP_201_CREATED)
async def create_automation(
    payload: AutomationCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    automation = await postgres.create_automation(db, payload)

    await write_audit_event(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        action="create_automation",
        result="success",
        tenant_id=payload.tenant_id,
        env=payload.env,
        automation_id=automation.id,
    )
    await db.commit()
    return automation


@router.get("", response_model=list[AutomationOut])
async def list_automations(
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    limit: int = Query(100, le=1000),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    items = await postgres.list_automations(db, tenant_id=tenant_id, env=env, limit=limit)
    return items


@router.get("/{automation_id}", response_model=AutomationOut)
async def get_automation(
    automation_id: str,
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    item = await postgres.get_automation(db, automation_id, tenant_id, env)
    if not item:
        raise HTTPException(status_code=404, detail="Automation not found")
    return item


@router.patch("/{automation_id}", response_model=AutomationOut)
async def update_automation(
    automation_id: str,
    payload: AutomationUpdate,
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    item = await postgres.update_automation(db, automation_id, tenant_id, env, payload)
    if not item:
        raise HTTPException(status_code=404, detail="Automation not found")

    await write_audit_event(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        action="update_automation",
        result="success",
        tenant_id=tenant_id,
        env=env,
        automation_id=item.id,
    )
    await db.commit()
    return item


@router.post(
    "/{automation_id}/run", response_model=AutomationRunOut, status_code=status.HTTP_202_ACCEPTED
)
async def trigger_run(
    automation_id: str,
    payload: TriggerRunRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    """Manually triggers a run for the given automation."""

    tenant_id = payload.tenant_id or identity.service_id
    env = payload.env or "prod"

    automation = await postgres.get_automation(db, automation_id, tenant_id, env)
    if not automation:
        raise HTTPException(
            status_code=404,
            detail=f"Automation {automation_id} not found for tenant={tenant_id} env={env}",
        )

    # Idempotency check
    existing = await postgres.get_run_by_idempotency_key(db, payload.idempotency_key)
    if existing:
        return AutomationRunOut.model_validate(existing)

    try:
        run = await postgres.create_run(
            db,
            tenant_id=tenant_id,
            env=env,
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id or identity.correlation_id,
            automation_id=automation.id,
        )
        await write_audit_event(
            db,
            correlation_id=identity.correlation_id,
            service_id=identity.service_id,
            action="trigger_run",
            result="success",
            tenant_id=tenant_id,
            env=env,
            automation_id=automation.id,
            run_id=run.id,
        )
        await db.commit()
        await db.refresh(run)

        # Telegram notification for manual triggers
        try:
            import os

            from apps.notifications_agent.client.notifications_client import NotificationsClient

            nc = NotificationsClient(
                base_url=os.getenv("NOTIFICATIONS_BASE_URL", "http://notifications-agent:8008"),
                service_id="automation-agent",
                api_key=os.getenv("NEXUS_NOTIF_AGENT_KEY", "nexus-notif-key-change-me"),
            )
            await nc.notify(
                tenant_id=tenant_id,
                env=env,
                severity="info",
                channels=["telegram"],
                subject="\u2699\ufe0f Automation Triggered",
                body=f"{automation.name} (manual run)",
                idempotency_key=f"auto-trigger:{run.id}",
            )
        except Exception:
            pass  # fire-and-forget

        return AutomationRunOut.model_validate(run)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
