from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import botocore.exceptions
import structlog

from apps.storage_agent.engine.secrets import get_secret
from apps.storage_agent.metrics import inc
from apps.storage_agent.store.postgres import StorageTarget

logger = structlog.get_logger(__name__)


class StorageOperationError(Exception):
    def __init__(self, message: str, code: str = "unknown_error"):
        super().__init__(message)
        self.code = code


@asynccontextmanager
async def _get_s3_client(target: StorageTarget, correlation_id: str) -> AsyncGenerator[Any, None]:
    """Provide a configured aioboto3 async client to the MinIO/S3 backend."""
    import aioboto3

    alias_ak = target.credential_aliases.get("access_key_id")
    alias_sk = target.credential_aliases.get("secret_access_key")
    if not alias_ak or not alias_sk:
        logger.error(
            "target_missing_credential_aliases",
            target_id=target.storage_target_id,
            correlation_id=correlation_id,
        )
        raise StorageOperationError(
            f"Target '{target.storage_target_id}' missing alias config for credentials",
            "missing_config",
        )

    ak = await get_secret(alias_ak, target.tenant_id or "nexus", target.env, correlation_id)
    sk = await get_secret(alias_sk, target.tenant_id or "nexus", target.env, correlation_id)

    if not ak or not sk:
        logger.error(
            "credentials_fetch_failed",
            target_id=target.storage_target_id,
            correlation_id=correlation_id,
        )
        raise StorageOperationError(
            f"Failed to fetch credentials for target '{target.storage_target_id}'", "auth_failed"
        )

    session = aioboto3.Session(
        aws_access_key_id=ak,
        aws_secret_access_key=sk,
        region_name=target.region or "us-east-1",
    )

    endpoint_url = target.endpoint_url if target.endpoint_url else None

    async with session.client("s3", endpoint_url=endpoint_url) as s3:
        yield s3


async def ensure_bucket(target: StorageTarget, bucket_name: str, correlation_id: str) -> bool:
    """Ensure the target bucket exists, creating it if necessary."""
    try:
        async with _get_s3_client(target, correlation_id) as s3:
            try:
                await s3.head_bucket(Bucket=bucket_name)
                inc("storage_ops_total", op="head_bucket", result="success")
                return True
            except botocore.exceptions.ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code == "404":
                    logger.info(
                        "bucket_not_found_creating",
                        bucket_name=bucket_name,
                        target_id=target.storage_target_id,
                    )
                    await s3.create_bucket(Bucket=bucket_name)
                    inc("storage_ops_total", op="create_bucket", result="success")
                    return True
                else:
                    inc("storage_ops_total", op="head_bucket", result="failed")
                    raise e
    except botocore.exceptions.ClientError as e:
        logger.error(
            "s3_client_error", error=str(e), op="ensure_bucket", correlation_id=correlation_id
        )
        raise StorageOperationError("Failed to ensure bucket", "s3_error")
    except StorageOperationError:
        raise
    except Exception as e:
        logger.error(
            "internal_error", error=str(e), op="ensure_bucket", correlation_id=correlation_id
        )
        raise StorageOperationError("Internal server error", "internal_error")


async def upload_object(
    target: StorageTarget,
    bucket_name: str,
    object_key: str,
    data: bytes,
    content_type: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Upload a byte stream straight to the target."""
    try:
        async with _get_s3_client(target, correlation_id) as s3:
            await s3.put_object(
                Bucket=bucket_name, Key=object_key, Body=data, ContentType=content_type
            )
            inc("storage_ops_total", op="put_object", result="success")

            # Re-fetch length directly
            head = await s3.head_object(Bucket=bucket_name, Key=object_key)
            return {"size_bytes": head.get("ContentLength", 0), "etag": head.get("ETag", "")}
    except Exception as e:
        logger.error("upload_failed", error=str(e)[:250], correlation_id=correlation_id)
        inc("storage_ops_total", op="put_object", result="failed")
        raise StorageOperationError("Upload failed", "s3_error")


async def generate_presigned_url(
    target: StorageTarget,
    bucket_name: str,
    object_key: str,
    method: str,
    expires_in: int,
    correlation_id: str,
) -> str:
    """Generate a presigned GET or PUT url."""
    op = "get_object" if method.upper() == "GET" else "put_object"
    try:
        async with _get_s3_client(target, correlation_id) as s3:
            url = await s3.generate_presigned_url(
                op, Params={"Bucket": bucket_name, "Key": object_key}, ExpiresIn=expires_in
            )
            inc("storage_ops_total", op="presign", result="success")
            return url
    except Exception as e:
        logger.error("presign_failed", error=str(e)[:250], correlation_id=correlation_id)
        inc("storage_ops_total", op="presign", result="failed")
        raise StorageOperationError("Presign failed", "s3_error")


async def delete_object(
    target: StorageTarget, bucket_name: str, object_key: str, correlation_id: str
) -> bool:
    """Delete a single object idempotently."""
    try:
        async with _get_s3_client(target, correlation_id) as s3:
            await s3.delete_object(Bucket=bucket_name, Key=object_key)
            inc("storage_ops_total", op="delete_object", result="success")
            return True
    except Exception as e:
        logger.error("delete_failed", error=str(e)[:250], correlation_id=correlation_id)
        inc("storage_ops_total", op="delete_object", result="failed")
        raise StorageOperationError("Delete failed", "s3_error")


async def list_objects(
    target: StorageTarget,
    bucket_name: str,
    prefix: str,
    max_keys: int,
    continuation_token: str | None,
    correlation_id: str,
) -> dict[str, Any]:
    """List objects in a bucket strictly by prefix, supporting pagination."""
    try:
        async with _get_s3_client(target, correlation_id) as s3:
            kwargs = {"Bucket": bucket_name, "Prefix": prefix, "MaxKeys": max_keys}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            resp = await s3.list_objects_v2(**kwargs)

            contents = []
            for obj in resp.get("Contents", []):
                contents.append(
                    {
                        "key": obj["Key"],
                        "size_bytes": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                    }
                )

            inc("storage_ops_total", op="list_objects", result="success")
            return {
                "keys": contents,
                "next_token": resp.get("NextContinuationToken"),
                "is_truncated": resp.get("IsTruncated", False),
            }
    except Exception as e:
        logger.error("list_failed", error=str(e)[:250], correlation_id=correlation_id)
        inc("storage_ops_total", op="list_objects", result="failed")
        raise StorageOperationError("List failed", "s3_error")
