import asyncio
from typing import Any, Dict
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.storage_agent.store.postgres import StorageJob, StorageJobResult, StorageTarget
from apps.storage_agent.engine import s3

logger = structlog.get_logger(__name__)


async def execute_retention_purge(
    db: AsyncSession,
    target: StorageTarget,
    bucket_name: str,
    prefix: str,
    older_than_days: int,
    dry_run: bool,
    correlation_id: str
) -> Dict[str, Any]:
    """Scan and delete objects older than `older_than_days` under a prefix."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    
    deleted_count = 0
    total_scanned = 0
    errors = 0
    
    continuation_token = None
    has_more = True
    
    while has_more:
        try:
             res = await s3.list_objects(
                 target=target,
                 bucket_name=bucket_name,
                 prefix=prefix,
                 max_keys=1000,
                 continuation_token=continuation_token,
                 correlation_id=correlation_id
             )
             keys = res.get("keys", [])
             continuation_token = res.get("next_token")
             has_more = res.get("is_truncated", False)
             
             for obj in keys:
                 total_scanned += 1
                 # S3 dates are ISO 8601 strings
                 last_mod = datetime.fromisoformat(obj["last_modified"].replace("Z", "+00:00"))
                 if last_mod < cutoff:
                     if not dry_run:
                         try:
                             # We do single deletes for simplicity/safety; batch deletes could be optimized
                             await s3.delete_object(target, bucket_name, obj["key"], correlation_id)
                             # Note: We should ideally string together DB record deletion here too
                             from apps.storage_agent.store import postgres
                             await postgres.delete_object_record(db, target.id, target.buckets[0].id, obj["key"]) 
                             db.commit() # Flush db
                         except Exception as e:
                             errors += 1
                             logger.error("retention_delete_failed", key=obj["key"], error=str(e)[:200])
                             continue
                     deleted_count += 1
                     
        except Exception as e:
            logger.error("retention_scan_failed", prefix=prefix, error=str(e)[:250])
            raise e

    return {
        "action": "retention_purge",
        "dry_run": dry_run,
        "bucket": bucket_name,
        "prefix": prefix,
        "cutoff_days": older_than_days,
        "scanned": total_scanned,
        "deleted": deleted_count,
        "errors": errors
    }
