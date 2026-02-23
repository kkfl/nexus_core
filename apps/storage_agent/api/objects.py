from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from structlog import get_logger

from apps.storage_agent.engine import s3
from apps.storage_agent.metrics import observe_latency
from apps.storage_agent.store import postgres

logger = get_logger(__name__)
router = APIRouter(tags=["objects"])


class PresignRequest(BaseModel):
    storage_target_id: str
    bucket_name: str
    object_key: str
    method: str = "GET"  # or PUT
    expires_in_seconds: int = 3600
    tenant_id: str = "nexus"
    env: str = "prod"


class ListObjectsRequest(BaseModel):
    storage_target_id: str
    bucket_name: str
    prefix: str = ""
    max_keys: int = 1000
    continuation_token: str | None = None
    tenant_id: str = "nexus"
    env: str = "prod"


class DeleteObjectsRequest(BaseModel):
    storage_target_id: str
    bucket_name: str
    object_keys: list[str]
    tenant_id: str = "nexus"
    env: str = "prod"


@router.post("/v1/objects/presign")
@observe_latency("api_request_latency_ms", route="/v1/objects/presign", method="POST")
async def presign_url(req: PresignRequest, db=Depends(postgres.get_db)):
    """Generate a presigned URL. Excellent for large file streaming directly to S3."""
    target = await postgres.get_target(db, req.storage_target_id, req.tenant_id, req.env)
    if not target:
        raise HTTPException(404, "storage_target_not_found")

    # Ensure maximum TTL is respected
    ttl = min(req.expires_in_seconds, 604800)  # 7 days max

    url = await s3.generate_presigned_url(
        target, req.bucket_name, req.object_key, req.method, ttl, "presign_gen"
    )
    return {
        "url": url,
        "expires_in": ttl,
        "method": req.method.upper(),
        "object_key": req.object_key,
    }


@router.post("/v1/objects/put")
@observe_latency("api_request_latency_ms", route="/v1/objects/put", method="POST")
async def put_object(
    storage_target_id: str = Form(...),
    bucket_name: str = Form(...),
    object_key: str = Form(...),
    tenant_id: str = Form("nexus"),
    env: str = Form("prod"),
    entity_type: str = Form(None),
    entity_id: str = Form(None),
    file: UploadFile = File(...),
    db=Depends(postgres.get_db),
):
    """Directly upload a small/medium payload, recording metadata in the db."""
    target = await postgres.get_target(db, storage_target_id, tenant_id, env)
    if not target:
        raise HTTPException(404, "target_not_found")

    b = await postgres.get_or_create_bucket(db, target.id, bucket_name, tenant_id, env)

    data = await file.read()

    res = await s3.upload_object(
        target, bucket_name, object_key, data, file.content_type, "put_obj"
    )

    # Register Record
    obj_rec = await postgres.register_object(
        db,
        tenant_id,
        env,
        target.id,
        b.id,
        object_key,
        file.content_type,
        res["size_bytes"],
        tags={},
        entity_type=entity_type,
        entity_id=entity_id,
    )
    await db.commit()

    return {
        "id": obj_rec.id,
        "object_key": obj_rec.object_key,
        "size_bytes": obj_rec.size_bytes,
        "etag": res.get("etag"),
    }


@router.post("/v1/objects/list")
@observe_latency("api_request_latency_ms", route="/v1/objects/list", method="POST")
async def list_objects(req: ListObjectsRequest, db=Depends(postgres.get_db)):
    target = await postgres.get_target(db, req.storage_target_id, req.tenant_id, req.env)
    if not target:
        raise HTTPException(404, "target_not_found")

    res = await s3.list_objects(
        target, req.bucket_name, req.prefix, req.max_keys, req.continuation_token, "list_obj"
    )
    return res


@router.post("/v1/objects/delete")
@observe_latency("api_request_latency_ms", route="/v1/objects/delete", method="POST")
async def delete_objects(req: DeleteObjectsRequest, db=Depends(postgres.get_db)):
    target = await postgres.get_target(db, req.storage_target_id, req.tenant_id, req.env)
    if not target:
        raise HTTPException(404, "target_not_found")

    b = await postgres.get_or_create_bucket(db, target.id, req.bucket_name, req.tenant_id, req.env)

    deleted_count = 0
    for key in req.object_keys:
        try:
            await s3.delete_object(target, req.bucket_name, key, "del_obj")
            await postgres.delete_object_record(db, target.id, b.id, key)
            deleted_count += 1
        except Exception as e:
            logger.error("batch_delete_item_failed", key=key, error=str(e))

    await db.commit()
    return {"deleted": deleted_count, "requested": len(req.object_keys)}
