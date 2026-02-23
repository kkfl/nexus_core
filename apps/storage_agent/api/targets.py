from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.storage_agent.store import postgres
from apps.storage_agent.engine import s3
from apps.storage_agent.metrics import observe_latency
from structlog import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["targets"])


class TargetUpsertRequest(BaseModel):
    storage_target_id: str
    tenant_id: str = "nexus"
    env: str = "prod"
    endpoint_url: str
    region: str
    default_bucket: str
    credential_aliases: Dict[str, str]
    flags: Dict[str, Any] = {}


class BucketEnsureRequest(BaseModel):
    storage_target_id: str
    bucket_name: str
    tenant_id: str = "nexus"
    env: str = "prod"


@router.post("/v1/targets")
@observe_latency("api_request_latency_ms", route="/v1/targets", method="POST")
async def upsert_target(req: TargetUpsertRequest, db=Depends(postgres.get_db)):
    """Upsert a new storage target configuration (no raw secrets, just aliases)."""
    # Validation
    if "access_key_id" not in req.credential_aliases or "secret_access_key" not in req.credential_aliases:
        raise HTTPException(400, "credential_aliases must contain access_key_id and secret_access_key pointers")

    logger.info("upserting_storage_target", target_id=req.storage_target_id, tenant_id=req.tenant_id, env=req.env)
    
    t = await postgres.upsert_target(
        db,
        tenant_id=req.tenant_id,
        env=req.env,
        storage_target_id=req.storage_target_id,
        endpoint_url=req.endpoint_url,
        region=req.region,
        default_bucket=req.default_bucket,
        credential_aliases=req.credential_aliases,
        flags=req.flags
    )
    await db.commit()
    
    return {
        "id": t.id,
        "storage_target_id": t.storage_target_id,
        "tenant_id": t.tenant_id,
        "env": t.env,
        "endpoint_url": t.endpoint_url,
        "region": t.region,
        "default_bucket": t.default_bucket,
        "enabled": t.enabled
    }


@router.get("/v1/targets")
@observe_latency("api_request_latency_ms", route="/v1/targets", method="GET")
async def list_targets(tenant_id: str = "nexus", env: str = "prod", db=Depends(postgres.get_db)):
    targets = await postgres.list_targets(db, tenant_id, env)
    return {
        "targets": [
            {
                "id": t.id,
                "storage_target_id": t.storage_target_id,
                "tenant_id": t.tenant_id,
                "env": t.env,
                "endpoint_url": t.endpoint_url,
                "region": t.region,
                "default_bucket": t.default_bucket,
                "enabled": t.enabled
            } for t in targets
        ]
    }


@router.post("/v1/buckets/ensure")
@observe_latency("api_request_latency_ms", route="/v1/buckets/ensure", method="POST")
async def ensure_bucket(req: BucketEnsureRequest, db=Depends(postgres.get_db)):
    """Idempotent bucket creation on the remote target."""
    target = await postgres.get_target(db, req.storage_target_id, req.tenant_id, req.env)
    if not target:
        raise HTTPException(404, "storage_target_not_found")
        
    logger.info("ensuring_bucket", target_id=req.storage_target_id, bucket=req.bucket_name)

    # Note: correlation ID would typically be passed down here from middleware context via structlog
    correlation_id = "bucket_ensure"
    
    try:
        success = await s3.ensure_bucket(target, req.bucket_name, correlation_id)
        if success:
            b = await postgres.get_or_create_bucket(db, target.id, req.bucket_name, target.tenant_id, target.env)
            await db.commit()
            return {"status": "success", "bucket_id": b.id, "bucket_name": b.bucket_name}
    except s3.StorageOperationError as e:
        logger.error("ensure_bucket_failed", error=str(e))
        raise HTTPException(500, f"Error ensuring bucket: {e}")
