import os
import json
import logging
import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, Request, HTTPException
import httpx
import aioboto3

from packages.shared.schemas.agent_sdk import AgentTaskRequest, AgentTaskResponse, AgentTaskError, ProposedWrite, JobSummary
from packages.shared.agent_sdk import handle_agent_execute

app = FastAPI(title="Storage Agent V1 (SDK)")
logger = logging.getLogger(__name__)

STORAGE_MOCK = os.getenv("STORAGE_MOCK", "false").lower() == "true"
NEXUS_BASE_URL = os.environ.get("NEXUS_BASE_URL", "http://nexus-api:8000")
NEXUS_AGENT_KEY = os.environ.get("NEXUS_AGENT_KEY", "internal-storage-key-demo")

ENABLE_STORAGE_WRITES = os.getenv("ENABLE_STORAGE_WRITES", "true").lower() == "true"
ENABLE_DELETES = os.getenv("ENABLE_DELETES", "false").lower() == "true"

async def _fetch_target_and_creds(target_id: str) -> tuple[Dict, str, str]:
    if STORAGE_MOCK and target_id == "mock":
        return {
            "endpoint_url": "http://minio:9000",
            "bucket": "mock-bucket",
            "region": "us-east-1",
            "base_prefix": "",
        }, "admin", "minio_pass"

    async with httpx.AsyncClient() as client:
        # 1. Fetch metadata & secret IDs
        r_meta = await client.get(
            f"{NEXUS_BASE_URL}/internal/storage/targets/{target_id}",
            headers={"X-Nexus-Internal": NEXUS_AGENT_KEY}
        )
        if r_meta.status_code != 200:
            raise Exception(f"Failed to fetch storage target: {r_meta.text}")
        target = r_meta.json()

        # 2. Fetch AK
        r_ak = await client.post(
            f"{NEXUS_BASE_URL}/internal/secrets/decrypt",
            headers={"X-Nexus-Internal": NEXUS_AGENT_KEY},
            json={"secret_id": target["access_key_id_secret_id"]}
        )
        if r_ak.status_code != 200:
            raise Exception("Failed to decrypt AK")
        ak = r_ak.json()["value"]

        # 3. Fetch SK
        r_sk = await client.post(
            f"{NEXUS_BASE_URL}/internal/secrets/decrypt",
            headers={"X-Nexus-Internal": NEXUS_AGENT_KEY},
            json={"secret_id": target["secret_access_key_secret_id"]}
        )
        if r_sk.status_code != 200:
            raise Exception("Failed to decrypt SK")
        sk = r_sk.json()["value"]

    return target, ak, sk

def _get_boto_session(ak: str, sk: str, region: str):
    return aioboto3.Session(
        aws_access_key_id=ak,
        aws_secret_access_key=sk,
        region_name=region or "us-east-1"
    )

async def _execute_handler(req: AgentTaskRequest) -> AgentTaskResponse:
    persona_received = {"name": req.persona.name, "version": req.persona.version} if req.persona else None
    ctx_count = len(req.context) if req.context else 0

    target_id = req.payload.get("storage_target_id")
    if not target_id:
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="missing_target", message="storage_target_id is required"))

    # Determine if READ or WRITE
    is_write = req.type in ("storage.copy", "storage.lifecycle.apply", "storage.delete")
    
    if req.type == "storage.lifecycle.propose":
        # Propose is technically read-only state generation in V1
        is_write = False

    # Guard writes
    if is_write:
        if not ENABLE_STORAGE_WRITES:
            return AgentTaskResponse(ok=False, error=AgentTaskError(code="writes_disabled_by_config", message="ENABLE_STORAGE_WRITES is false"))
        if req.type == "storage.delete" and not ENABLE_DELETES:
             return AgentTaskResponse(ok=False, error=AgentTaskError(code="writes_disabled_by_config", message="ENABLE_DELETES is false"))
             
        # Check KI persona allowed_capabilities
        allowed = []
        if req.persona and req.persona.tools_policy:
            allowed = req.persona.tools_policy.get("allowed_capabilities", [])
        if req.type not in allowed:
            return AgentTaskResponse(ok=False, error=AgentTaskError(code="persona_policy_violation", message=f"{req.type} not in allowed_capabilities"))

    # Default to READ
    if not is_write and req.persona and req.persona.tools_policy:
        allowed = req.persona.tools_policy.get("allowed_capabilities", [])
        if req.type not in allowed and req.type.startswith("storage."):
            # Maybe restrict READ too if extremely strict, but V1 says "if persona missing: allow only READ"
             pass

    try:
        # Determine src credentials
        target, ak, sk = await _fetch_target_and_creds(target_id)
        session = _get_boto_session(ak, sk, target.get("region"))
        endpoint_url = target.get("endpoint_url")
        bucket = target.get("bucket")
        base_prefix = target.get("base_prefix", "")
        
        # Merge payload prefix with base prefix
        request_prefix = req.payload.get("prefix", "")
        full_prefix = os.path.join(base_prefix, request_prefix) if request_prefix else base_prefix
        if full_prefix.startswith("/"): full_prefix = full_prefix[1:]

        proposed_writes = []
        job_summary = None

        async with session.client("s3", endpoint_url=endpoint_url) as s3:
            
            if req.type == "storage.list":
                max_keys = req.payload.get("max_keys", 1000)
                continuation_token = req.payload.get("continuation_token")
                call_args = {"Bucket": bucket, "Prefix": full_prefix, "MaxKeys": max_keys}
                if continuation_token:
                    call_args["ContinuationToken"] = continuation_token
                    
                resp = await s3.list_objects_v2(**call_args)
                
                keys = []
                for obj in resp.get("Contents", []):
                    keys.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat()
                    })
                    
                result_data = {
                    "persona_received": persona_received,
                    "context_received_count": ctx_count,
                    "keys": keys,
                    "count": len(keys),
                    "next_token": resp.get("NextContinuationToken")
                }
                
                return AgentTaskResponse(ok=True, result=result_data, proposed_writes=None)

            elif req.type == "storage.head":
                key = req.payload.get("key")
                if not key: raise Exception("Missing key")
                if base_prefix and not key.startswith(base_prefix):
                    key = os.path.join(base_prefix, key)
                    
                resp = await s3.head_object(Bucket=bucket, Key=key)
                
                result_data = {
                    "persona_received": persona_received,
                    "context_received_count": ctx_count,
                    "size": resp.get("ContentLength"),
                    "etag": resp.get("ETag"),
                    "content_type": resp.get("ContentType"),
                    "last_modified": resp.get("LastModified").isoformat()
                }
                return AgentTaskResponse(ok=True, result=result_data)

            elif req.type == "storage.presign.get":
                key = req.payload.get("key")
                expires = req.payload.get("expires_seconds", 3600)
                if not key: raise Exception("Missing key")
                if base_prefix and not key.startswith(base_prefix):
                    key = os.path.join(base_prefix, key)
                    
                url = await s3.generate_presigned_url(
                    ClientMethod='get_object',
                    Params={'Bucket': bucket, 'Key': key},
                    ExpiresIn=expires
                )
                result_data = {
                    "persona_received": persona_received,
                    "context_received_count": ctx_count,
                    "url": url,
                    "expires_in": expires
                }
                return AgentTaskResponse(ok=True, result=result_data)

            elif req.type == "storage.stats.prefix":
                max_scan_keys = req.payload.get("max_scan_keys", 10000)
                
                # Bounded scan
                paginator = s3.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(
                    Bucket=bucket,
                    Prefix=full_prefix,
                    PaginationConfig={'MaxItems': max_scan_keys}
                )
                
                total_bytes = 0
                object_count = 0
                
                async for page in page_iterator:
                    for obj in page.get("Contents", []):
                        object_count += 1
                        total_bytes += obj["Size"]
                        
                pw = ProposedWrite(
                    entity_kind="storage_prefix",
                    external_ref=f"{target_id}:{full_prefix}",
                    action="upsert",
                    patch={
                        "storage_target_id": target_id,
                        "prefix": full_prefix,
                        "object_count": object_count,
                        "total_bytes": total_bytes,
                        "sampled_at": datetime.datetime.utcnow().isoformat()
                    },
                    idempotency_key=f"stats:{target_id}:{full_prefix}:{datetime.datetime.utcnow().timestamp()}"
                )
                
                result_data = {
                    "persona_received": persona_received,
                    "context_received_count": ctx_count,
                    "object_count": object_count,
                    "total_bytes": total_bytes,
                    "prefix": full_prefix
                }
                return AgentTaskResponse(ok=True, result=result_data, proposed_writes=[pw])

            elif req.type == "storage.copy":
                idem_key = req.payload.get("idempotency_key")
                if not idem_key: raise Exception("Missing idempotency_key")
                
                src = req.payload.get("src", {})
                dst = req.payload.get("dst", {})
                
                src_target_id = src.get("storage_target_id", target_id)
                dst_target_id = dst.get("storage_target_id", target_id)
                
                # Fetch dst target if different
                if src_target_id != dst_target_id:
                     dst_target, dst_ak, dst_sk = await _fetch_target_and_creds(dst_target_id)
                     dst_session = _get_boto_session(dst_ak, dst_sk, dst_target.get("region"))
                     dst_endpoint = dst_target.get("endpoint_url")
                     dst_bucket = dst_target.get("bucket")
                else:
                     dst_target = target
                     dst_session = session
                     dst_endpoint = endpoint_url
                     dst_bucket = bucket
                
                src_key = src.get("key")
                dst_key = dst.get("key")
                
                # Server side copy normally, but if cross-endpoint, we'd need streaming.
                # V1: Assume single-endpoint or standard S3 behavior where CopySource is sufficient,
                # or we just stream it manually if endpoints differ.
                if src_target_id != dst_target_id and endpoint_url != dst_endpoint:
                     # Stream bytes (slow, but safe fallback)
                     resp = await s3.get_object(Bucket=bucket, Key=src_key)
                     async with dst_session.client("s3", endpoint_url=dst_endpoint) as dst_s3:
                          await dst_s3.put_object(Bucket=dst_bucket, Key=dst_key, Body=await resp['Body'].read())
                     bytes_copied = resp.get("ContentLength", 0)
                else:
                     # standard copy
                     copy_source = {'Bucket': bucket, 'Key': src_key}
                     resp = await s3.copy_object(CopySource=copy_source, Bucket=dst_bucket, Key=dst_key)
                     # get size for summary
                     head = await s3.head_object(Bucket=dst_bucket, Key=dst_key)
                     bytes_copied = head.get("ContentLength", 0)
                     
                job_summary = JobSummary(
                    kind="copy",
                    status="succeeded",
                    details={"src_bucket": bucket, "src_key": src_key, "dst_bucket": dst_bucket, "dst_key": dst_key, "bytes": bytes_copied}
                )
                
                result_data = {"persona_received": persona_received, "bytes_copied": bytes_copied, "status": "success"}
                return AgentTaskResponse(ok=True, result=result_data, job_summary=job_summary)

            elif req.type == "storage.lifecycle.propose":
                rules = req.payload.get("rules", {})
                
                s3_rules = []
                import hashlib
                rule_id = hashlib.md5(f"{full_prefix}-{rules}".encode()).hexdigest()[:8]
                
                rule = {
                    "ID": f"Propose-{rule_id}",
                    "Prefix": full_prefix,
                    "Status": "Enabled",
                }
                
                exp_days = rules.get("expire_days")
                if exp_days:
                    rule["Expiration"] = {"Days": exp_days}
                    
                trans_days = rules.get("transition_days")
                if trans_days:
                    # Generic to Glacier
                    rule["Transitions"] = [{"Days": trans_days, "StorageClass": "GLACIER"}]
                    
                nc_exp = rules.get("noncurrent_expire_days")
                if nc_exp:
                    rule["NoncurrentVersionExpiration"] = {"NoncurrentDays": nc_exp}
                    
                s3_rules.append(rule)
                
                policy = {"Rules": s3_rules}
                
                pw = ProposedWrite(
                    entity_kind="storage_prefix",
                    external_ref=f"{target_id}:{full_prefix}",
                    action="upsert",
                    patch={
                        "storage_target_id": target_id,
                        "prefix": full_prefix,
                        "retention_proposal": policy,
                        "proposal_date": datetime.datetime.utcnow().isoformat()
                    },
                    idempotency_key=f"lifecycle_prop:{target_id}:{full_prefix}:{datetime.datetime.utcnow().timestamp()}"
                )
                
                job_summary = JobSummary(
                    kind="lifecycle_propose",
                    status="succeeded",
                    details={"policy": policy, "prefix": full_prefix}
                )

                result_data = {
                    "persona_received": persona_received,
                    "context_received_count": ctx_count,
                    "policy": policy,
                    "dry_run": req.payload.get("dry_run", True)
                }
                return AgentTaskResponse(ok=True, result=result_data, proposed_writes=[pw], job_summary=job_summary)

            elif req.type == "storage.lifecycle.apply":
                idem_key = req.payload.get("idempotency_key")
                if not idem_key: raise Exception("Missing idempotency_key")
                
                policy = req.payload.get("policy")
                
                # Fetch existing to merge or just overwrite? (S3 overwrites bucket lifecycle)
                # For safety, in V1 we will just put this single policy to the bucket.
                await s3.put_bucket_lifecycle_configuration(
                    Bucket=bucket,
                    LifecycleConfiguration=policy
                )
                
                job_summary = JobSummary(
                    kind="lifecycle_apply",
                    status="succeeded",
                    details={"policy": policy}
                )
                
                result_data = {
                    "persona_received": persona_received,
                    "applied": True,
                    "bucket": bucket
                }
                return AgentTaskResponse(ok=True, result=result_data, job_summary=job_summary)
            
            elif req.type == "storage.delete":
                idem_key = req.payload.get("idempotency_key")
                if not idem_key: raise Exception("Missing idempotency_key")
                
                key = req.payload.get("key")
                if not key: raise Exception("Missing key")
                if base_prefix and not key.startswith(base_prefix):
                    key = os.path.join(base_prefix, key)
                    
                await s3.delete_object(Bucket=bucket, Key=key)
                
                job_summary = JobSummary(
                    kind="delete",
                    status="succeeded",
                    details={"bucket": bucket, "key": key}
                )
                
                result_data = {
                    "persona_received": persona_received,
                    "deleted": True,
                    "key": key
                }
                return AgentTaskResponse(ok=True, result=result_data, job_summary=job_summary)

            else:
                 return AgentTaskResponse(ok=False, error=AgentTaskError(code="unknown_task", message=f"Task {req.type} not supported"))

    except Exception as e:
        logger.error(f"Execution failed: {e}", exc_info=True)
        return AgentTaskResponse(ok=False, error=AgentTaskError(code="execution_failed", message=str(e)))

@app.post("/execute", response_model=AgentTaskResponse)
async def execute_task(req: AgentTaskRequest, request: Request):
    return await handle_agent_execute(req, request, _execute_handler)

@app.get("/capabilities")
async def get_capabilities():
    return {
        "capabilities": [
            "storage.list",
            "storage.head",
            "storage.presign.get",
            "storage.stats.prefix",
            "storage.copy",
            "storage.lifecycle.propose",
            "storage.lifecycle.apply",
            "storage.delete"
        ],
        "version": "1.0.0"
    }

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
