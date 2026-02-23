import asyncio
from datetime import datetime, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exc

from apps.carrier_agent.store.database import async_session
from apps.carrier_agent.models import CarrierJob, CarrierJobResult, CarrierAuditEvent, CarrierTarget

logger = structlog.get_logger(__name__)

async def _process_job(db: AsyncSession, job: CarrierJob) -> None:
    start_time = datetime.now(timezone.utc)
    logger.info("carrier_job_processing_start", job_id=job.id, action=job.action)
    try:
        res = await db.execute(select(CarrierTarget).where(CarrierTarget.id == job.carrier_target_id))
        target = res.scalars().first()
        if not target:
            raise ValueError(f"Target '{job.carrier_target_id}' missing from DB")
            
        output = {"action": job.action, "status": "executed"}
        duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        
        result = CarrierJobResult(job_id=job.id, output_summary_safe=output)
        db.add(result)
        job.status = "succeeded"

        audit = CarrierAuditEvent(
            correlation_id=job.correlation_id,
            service_id="carrier-agent-runner",
            tenant_id=job.tenant_id,
            env=job.env,
            action=f"job.{job.action}",
            target_id=target.id,
            result="success"
        )
        db.add(audit)

    except Exception as e:
        logger.exception("carrier_job_panic", job_id=job.id)
        duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        result = CarrierJobResult(
            job_id=job.id,
            output_summary_safe={"error": str(e)}
        )
        db.add(result)
        job.status = "failed"
        audit = CarrierAuditEvent(
            correlation_id=job.correlation_id,
            service_id="carrier-agent-runner",
            tenant_id=job.tenant_id,
            env=job.env,
            action=f"job.{job.action}",
            target_id=job.carrier_target_id,
            result="error",
            reason=str(e)[:500]
        )
        db.add(audit)
    await db.commit()

async def poll_jobs() -> None:
    try:
        async with async_session() as db:
            stmt = select(CarrierJob).where(CarrierJob.status == "pending")\
                                 .order_by(CarrierJob.created_at.asc())\
                                 .with_for_update(skip_locked=True)\
                                 .limit(1)
            res = await db.execute(stmt)
            job = res.scalars().first()
            if not job:
                return
            job.status = "running"
            job.attempts += 1
            await db.commit()
            await _process_job(db, job)
    except exc.SQLAlchemyError as e:
        logger.error("carrier_job_db_error", error=str(e))
    except Exception as e:
        logger.exception("carrier_job_polling_error", error=str(e))

async def run_worker_loop(tick_interval: int = 5) -> None:
    logger.info("carrier_job_worker_started", interval=tick_interval)
    while True:
        await poll_jobs()
        await asyncio.sleep(tick_interval)
