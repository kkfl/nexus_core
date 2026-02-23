import asyncio
import structlog
from datetime import datetime, timezone

from apps.automation_agent.store.database import Base
from apps.automation_agent.store.postgres import get_pending_runs, create_step_runs, create_dlq_entry
from apps.automation_agent.models import AutomationRun
from apps.automation_agent.executor.templating import extract_variables, render_dict
from apps.automation_agent.executor.http import execute_agent_action
from apps.automation_agent.redaction.logs import ensure_safe_output
from apps.automation_agent.client.notifications import send_notification
from apps.automation_agent.audit.log import write_audit_event

logger = structlog.get_logger(__name__)

async def process_run(db, run: AutomationRun):
    """
    Executes a single automation run.
    """
    now = datetime.now(timezone.utc)
    run.status = "running"
    run.started_at = now
    await db.commit()
    
    automation = run.automation
    if not automation:
        run.status = "failed"
        run.error_summary = "Parent automation definition not found"
        run.ended_at = datetime.now(timezone.utc)
        await db.commit()
        return

    spec = automation.workflow_spec
    steps = spec.get("steps", [])
    
    logger.info("processing_run_started", run_id=run.id, automation_id=automation.id, steps=len(steps))
    
    # 1. Create step records
    step_runs = await create_step_runs(db, run.id, steps)
    
    # Context injected across steps
    context = extract_variables(
        run_id=run.id,
        tenant_id=run.tenant_id,
        env=run.env,
        custom_inputs={}  # In V1 MVP, manual overrides from API can be added here if we expand trigger struct
    )

    run_success = True
    error_summary = None

    for i, step_def in enumerate(steps):
        step_run = step_runs[i]
        step_run.status = "running"
        step_run.started_at = datetime.now(timezone.utc)
        await db.commit()
        
        step_id = step_def["step_id"]
        agent_name = step_def["agent_name"]
        action = step_def["action"]
        raw_input = step_def.get("input", {})
        timeout = step_def.get("timeout_seconds", 30)
        
        retry_policy = step_def.get("retry_policy", {"max_attempts": 1, "backoff_ms": 1000})
        max_attempts = retry_policy.get("max_attempts", 1)
        backoff_ms = retry_policy.get("backoff_ms", 1000)

        step_success = False
        final_output = None
        last_err = None

        # Template input
        try:
            rendered_input = render_dict(raw_input, context)
        except Exception as e:
            rendered_input = {"_templating_error": str(e)}
            last_err = f"Templating failed: {e}"
            max_attempts = 1 # don't retry bad templates

        if not last_err:
            for attempt in range(1, max_attempts + 1):
                step_run.attempt = attempt
                await db.commit()
                
                success, output = await execute_agent_action(
                    agent_name=agent_name,
                    action=action,
                    input_data=rendered_input,
                    tenant_id=run.tenant_id,
                    env=run.env,
                    correlation_id=run.correlation_id,
                    timeout_seconds=timeout
                )
                
                if success:
                    step_success = True
                    final_output = output
                    break
                else:
                    last_err = str(output)
                    if attempt < max_attempts:
                        await asyncio.sleep(backoff_ms / 1000.0)
                        
        step_run.ended_at = datetime.now(timezone.utc)
        step_run.duration_ms = int((step_run.ended_at - step_run.started_at).total_seconds() * 1000)
        
        if step_success:
            step_run.status = "succeeded"
            step_run.output_summary = ensure_safe_output(final_output)
            context["steps"][step_id] = {"output": final_output, "status": "succeeded"}
        else:
            step_run.status = "failed"
            step_run.last_error_redacted = last_err
            run_success = False
            error_summary = f"Step '{step_id}' failed: {last_err}"
            context["steps"][step_id] = {"status": "failed", "error": last_err}
            await db.commit()
            break # Halt workflow on first step failure (sequential MVP)
            
    run.ended_at = datetime.now(timezone.utc)
    
    if run_success:
        run.status = "succeeded"
        
        await write_audit_event(
            db, correlation_id=run.correlation_id, service_id="automation-agent",
            action="run_workflow", result="success",
            tenant_id=run.tenant_id, env=run.env,
            automation_id=automation.id, run_id=run.id
        )
        
        if automation.notify_on_success:
            await send_notification(
                tenant_id=run.tenant_id, env=run.env,
                severity="info", template_id="generic",
                context={"subject": f"Automation Succeeded: {automation.name}", "body": f"Run {run.id} completed successfully."},
                correlation_id=run.correlation_id,
                idempotency_key=f"notify_success_{run.id}"
            )
            
    else:
        run.status = "failed"
        run.error_summary = error_summary
        
        # DLQ
        await create_dlq_entry(db, run.id)
        
        await write_audit_event(
            db, correlation_id=run.correlation_id, service_id="automation-agent",
            action="run_workflow", result="failure", detail=error_summary,
            tenant_id=run.tenant_id, env=run.env,
            automation_id=automation.id, run_id=run.id
        )
        
        if automation.notify_on_failure:
            await send_notification(
                tenant_id=run.tenant_id, env=run.env,
                severity="critical", template_id="generic",
                context={"subject": f"Automation Failed: {automation.name}", "body": f"Run {run.id} failed.\nError: {error_summary}"},
                correlation_id=run.correlation_id,
                idempotency_key=f"notify_failure_{run.id}"
            )

    await db.commit()
    logger.info("processing_run_completed", run_id=run.id, status=run.status)


async def worker_loop(get_db_session_func, tick_interval_sec: int = 5, concurrency: int = 5):
    """
    Pulls pending runs and executes them.
    In MVP this is a simple polling loop.
    """
    logger.info("worker_loop_started", concurrency=concurrency)
    
    semaphore = asyncio.Semaphore(concurrency)
    
    async def process_with_semaphore(run_id: str):
        async with semaphore:
            try:
                async for db in get_db_session_func():
                    from apps.automation_agent.store.postgres import get_run
                    from sqlalchemy.orm import joinedload
                    stmt = __import__("sqlalchemy").select(AutomationRun).options(joinedload(AutomationRun.automation)).where(AutomationRun.id == run_id)
                    res = await db.execute(stmt)
                    run = res.scalar_one_or_none()
                    if run and run.status in ("pending", "running"):
                        await process_run(db, run)
                    break
            except Exception as e:
                logger.error("process_run_failed", run_id=run_id, error=str(e), exc_info=True)
                
    while True:
        try:
            tasks = []
            async for db in get_db_session_func():
                # Pull pending runs
                pending = await get_pending_runs(db, limit=concurrency)
                
                # We mark them "running" immediately so other workers don't pick them if multi-tenant UI scales
                for run in pending:
                    run.status = "running"
                await db.commit()
                
                for run in pending:
                    tasks.append(asyncio.create_task(process_with_semaphore(run.id)))
                break
                
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error("worker_loop_error", error=str(e))
            
        # Give DB connection back and sleep
        await asyncio.sleep(tick_interval_sec)
