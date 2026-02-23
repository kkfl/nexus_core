from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from structlog import get_logger

from apps.storage_agent.engine import alerter, retention
from apps.storage_agent.metrics import observe_latency
from apps.storage_agent.store import postgres

logger = get_logger(__name__)
router = APIRouter(tags=["jobs"])


class RetentionJobRequest(BaseModel):
    storage_target_id: str
    bucket_name: str
    prefix: str = ""
    older_than_days: int = 30
    dry_run: bool = False
    tenant_id: str = "nexus"
    env: str = "prod"


@router.post("/v1/retention/execute")
@observe_latency("api_request_latency_ms", route="/v1/retention/execute", method="POST")
async def execute_retention_job(
    req: RetentionJobRequest, background_tasks: BackgroundTasks, db=Depends(postgres.get_db)
):
    """Async execution of a retention job. Yields immediately. Result notifies Telegram."""

    target = await postgres.get_target(db, req.storage_target_id, req.tenant_id, req.env)
    if not target:
        raise HTTPException(404, "target_not_found")

    # Generate mock correlation ID for background tasks
    import uuid

    correlation_id = str(uuid.uuid4())

    # Normally we'd queue in the DB (StorageJobs), but for this V1 we run it as a BackgroundTask
    async def bg_retention_task():
        # Open fresh DB session
        async for s_db in postgres.get_db():
            try:
                # Reload target
                t = await postgres.get_target(s_db, req.storage_target_id, req.tenant_id, req.env)
                res = await retention.execute_retention_purge(
                    s_db,
                    target=t,
                    bucket_name=req.bucket_name,
                    prefix=req.prefix,
                    older_than_days=req.older_than_days,
                    dry_run=req.dry_run,
                    correlation_id=correlation_id,
                )
                await s_db.commit()

                # We optionally notify if configured... Let's just notify success for V1
                body = (
                    f"Storage Retention {'Dry-Run ' if req.dry_run else ''}Completed\n"
                    f"Target: {req.storage_target_id}/{req.bucket_name}/{req.prefix}\n"
                    f"Scanned: {res['scanned']}, Deleted: {res['deleted']}, Errors: {res['errors']}"
                )

                await alerter.dispatch_alert(
                    req.tenant_id,
                    req.env,
                    "Storage Retention Passed",
                    body,
                    channel="telegram",
                    correlation_id=correlation_id,
                )

            except Exception as e:
                logger.error(
                    "bg_retention_task_failed", error=str(e), correlation_id=correlation_id
                )
                # Dispatch error
                body = f"Retention failed on {req.storage_target_id}. Error: {str(e)[:250]}"
                await alerter.dispatch_alert(
                    req.tenant_id,
                    req.env,
                    "Storage Retention FAILED",
                    body,
                    channel="telegram",
                    correlation_id=correlation_id,
                )

    background_tasks.add_task(bg_retention_task)
    return {
        "status": "accepted",
        "job_type": "retention_purge",
        "correlation_id": correlation_id,
        "dry_run": req.dry_run,
    }
