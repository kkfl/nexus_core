from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.automation_agent.models import Automation, AutomationDLQ, AutomationRun, AutomationStepRun
from apps.automation_agent.schemas import AutomationCreate, AutomationUpdate


async def create_automation(db: AsyncSession, create_model: AutomationCreate) -> Automation:
    automation = Automation(
        tenant_id=create_model.tenant_id,
        env=create_model.env,
        name=create_model.name,
        description=create_model.description,
        schedule_cron=create_model.schedule_cron,
        enabled=create_model.enabled,
        workflow_spec=create_model.workflow_spec.model_dump(),
        max_concurrent_runs=create_model.max_concurrent_runs,
        notify_on_failure=create_model.notify_on_failure,
        notify_on_success=create_model.notify_on_success,
    )
    db.add(automation)
    await db.flush()
    return automation


async def get_automation(
    db: AsyncSession, automation_id: str, tenant_id: str, env: str
) -> Automation | None:
    stmt = select(Automation).where(
        Automation.id == automation_id, Automation.tenant_id == tenant_id, Automation.env == env
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_automations(
    db: AsyncSession, tenant_id: str, env: str, limit: int = 100
) -> list[Automation]:
    stmt = (
        select(Automation)
        .where(Automation.tenant_id == tenant_id, Automation.env == env)
        .order_by(desc(Automation.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_due_cron_automations(db: AsyncSession) -> list[Automation]:
    # Returns all enabled automations with a cron schedule
    stmt = select(Automation).where(
        Automation.enabled is True, Automation.schedule_cron.isnot(None)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_automation(
    db: AsyncSession, automation_id: str, tenant_id: str, env: str, update_model: AutomationUpdate
) -> Automation | None:
    automation = await get_automation(db, automation_id, tenant_id, env)
    if not automation:
        return None

    update_data = update_model.model_dump(exclude_unset=True)
    if "workflow_spec" in update_data and update_data["workflow_spec"] is not None:
        update_data["workflow_spec"] = update_model.workflow_spec.model_dump()

    for key, value in update_data.items():
        setattr(automation, key, value)

    await db.flush()
    return automation


# -----------------------------------------------------------------------------
# Run Tracking
# -----------------------------------------------------------------------------


async def get_run_by_idempotency_key(
    db: AsyncSession, idempotency_key: str
) -> AutomationRun | None:
    stmt = select(AutomationRun).where(AutomationRun.idempotency_key == idempotency_key)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_run(
    db: AsyncSession,
    tenant_id: str,
    env: str,
    idempotency_key: str,
    correlation_id: str,
    automation_id: str | None = None,
) -> AutomationRun:
    run = AutomationRun(
        automation_id=automation_id,
        tenant_id=tenant_id,
        env=env,
        status="pending",
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
    db.add(run)
    await db.flush()
    return run


async def create_step_runs(
    db: AsyncSession, run_id: str, steps: list[dict[str, Any]]
) -> list[AutomationStepRun]:
    step_runs = []
    for step in steps:
        step_run = AutomationStepRun(
            run_id=run_id,
            step_id=step["step_id"],
            status="pending",
            target_agent=step["agent_name"],
        )
        db.add(step_run)
        step_runs.append(step_run)
    await db.flush()
    return step_runs


async def get_run(db: AsyncSession, run_id: str, tenant_id: str, env: str) -> AutomationRun | None:
    stmt = select(AutomationRun).where(
        AutomationRun.id == run_id, AutomationRun.tenant_id == tenant_id, AutomationRun.env == env
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_runs(
    db: AsyncSession, tenant_id: str, env: str, limit: int = 50
) -> list[AutomationRun]:
    stmt = (
        select(AutomationRun)
        .where(AutomationRun.tenant_id == tenant_id, AutomationRun.env == env)
        .order_by(desc(AutomationRun.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_pending_runs(db: AsyncSession, limit: int = 20) -> list[AutomationRun]:
    # Used by the worker to pull pending runs for execution
    stmt = (
        select(AutomationRun)
        .where(AutomationRun.status == "pending")
        .order_by(AutomationRun.created_at)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_dlq_entry(db: AsyncSession, run_id: str) -> AutomationDLQ:
    dlq = AutomationDLQ(run_id=run_id)
    db.add(dlq)
    await db.flush()
    return dlq
