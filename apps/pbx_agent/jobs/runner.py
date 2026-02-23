"""
Background async worker that pulls 'pending' jobs from DB,
runs the mutating AMI command (e.g. reload), and updates job state + audit log.
"""

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import exc, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.adapters.ami import AmiError, run_ami_action
from apps.pbx_agent.client.secrets import SecretsError, fetch_secret
from apps.pbx_agent.models import PbxAuditEvent, PbxJob, PbxJobResult, PbxTarget
from apps.pbx_agent.store.database import async_session

logger = structlog.get_logger(__name__)


async def _process_job(db: AsyncSession, job: PbxJob) -> None:
    """Execute a single job and write its result."""
    start_time = datetime.now(UTC)
    logger.info("pbx_job_processing_start", job_id=job.id, action=job.action)

    try:
        # Load the target fully
        res = await db.execute(select(PbxTarget).where(PbxTarget.id == job.pbx_target_id))
        target = res.scalars().first()
        if not target:
            raise ValueError(f"Target '{job.pbx_target_id}' missing from DB")

        # Fetch AMI secret securely
        secret = await fetch_secret(
            alias=target.ami_secret_alias,
            tenant_id=job.tenant_id,
            env=job.env,
            reason=f"job.{job.action}",
            correlation_id=job.correlation_id,
        )

        output = ""
        # Currently only `reload` is supported in V1
        if job.action == "reload":
            # Real AMI core reload. For FreePBX/Asterisk, action: Reload
            output = await run_ami_action(
                host=target.host,
                port=target.ami_port,
                username=target.ami_username,
                secret=secret,
                action_name="Reload",
            )
        else:
            raise NotImplementedError(f"Action '{job.action}' not implemented in runner")

        # Success path
        duration = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
        result = PbxJobResult(
            job_id=job.id,
            output_summary={"action": job.action, "output": output},
            duration_ms=duration,
        )
        db.add(result)
        job.status = "succeeded"

        # Record audit success
        audit = PbxAuditEvent(
            correlation_id=job.correlation_id,
            service_id="pbx-agent-runner",
            tenant_id=job.tenant_id,
            env=job.env,
            action=f"job.{job.action}",
            target_id=target.id,
            result="success",
        )
        db.add(audit)

    except (ValueError, NotImplementedError, SecretsError, AmiError) as e:
        # Known runtime or network errors
        await _record_failure(db, job, start_time, str(e), is_fatal=True)

    except Exception as e:
        # Unknown panic, retry logic could go here, but for V1 we fail it
        logger.exception("pbx_job_panic", job_id=job.id)
        await _record_failure(db, job, start_time, f"System error: {str(e)}", is_fatal=True)

    await db.commit()


async def _record_failure(
    db: AsyncSession, job: PbxJob, start_time: datetime, reason: str, is_fatal: bool
) -> None:
    duration = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
    result = PbxJobResult(job_id=job.id, error_redacted=reason, duration_ms=duration)
    db.add(result)
    job.status = "failed" if is_fatal else "retry"

    audit = PbxAuditEvent(
        correlation_id=job.correlation_id,
        service_id="pbx-agent-runner",
        tenant_id=job.tenant_id,
        env=job.env,
        action=f"job.{job.action}",
        target_id=job.pbx_target_id,
        result="error",
        detail=reason,
    )
    db.add(audit)


async def poll_jobs() -> None:
    """Fetch next pending job and execute it."""
    try:
        async with async_session() as db:
            # Atomic subquery lock to get exactly 1 job safely
            stmt = (
                select(PbxJob)
                .where(PbxJob.status == "pending")
                .order_by(PbxJob.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            res = await db.execute(stmt)
            job = res.scalars().first()

            if not job:
                return  # Queue is empty

            job.status = "running"
            job.attempts += 1
            await db.commit()

            # Now execute it
            await _process_job(db, job)

    except exc.SQLAlchemyError as e:
        logger.error("pbx_job_polling_db_error", error=str(e))
    except Exception as e:
        logger.exception("pbx_job_polling_error", error=str(e))


async def run_worker_loop(tick_interval: int = 5) -> None:
    """Infinite loop for the background task runner."""
    logger.info("pbx_job_worker_started", interval=tick_interval)
    while True:
        await poll_jobs()
        await asyncio.sleep(tick_interval)
