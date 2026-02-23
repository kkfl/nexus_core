"""
Diagnostics API — POST /v1/diagnostics/{check}
Real-time checks against a PBX target (no job queue — immediate response).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.adapters.ami import AmiError
from apps.pbx_agent.audit.log import write_audit_event
from apps.pbx_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.pbx_agent.client.secrets import SecretsError, fetch_secret
from apps.pbx_agent.ops.diagnostics import diagnostic_ami_check, diagnostic_ping, diagnostic_version
from apps.pbx_agent.schemas import TargetRequest
from apps.pbx_agent.store import postgres
from apps.pbx_agent.store.database import get_db

router = APIRouter(prefix="/v1/diagnostics", tags=["diagnostics"])


async def _resolve_target(db, req: TargetRequest):
    target = await postgres.get_target(db, req.pbx_target_id, req.tenant_id, req.env)
    if not target:
        raise HTTPException(status_code=404, detail=f"Target '{req.pbx_target_id}' not found")
    return target


@router.post("/ping")
async def ping(
    req: TargetRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target = await _resolve_target(db, req)
    result = await diagnostic_ping(target.host, target.ami_port)
    await write_audit_event(
        db,
        req.correlation_id or identity.correlation_id,
        identity.service_id,
        "diagnostics.ping",
        "success",
        tenant_id=req.tenant_id,
        env=req.env,
        target_id=target.id,
    )
    await db.commit()
    return result


@router.post("/ami-check")
async def ami_check(
    req: TargetRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target = await _resolve_target(db, req)
    ami_secret = None
    try:
        ami_secret = await fetch_secret(
            alias=target.ami_secret_alias,
            tenant_id=req.tenant_id,
            env=req.env,
            reason="diagnostics.ami_check",
            correlation_id=req.correlation_id or identity.correlation_id,
        )
    except SecretsError as e:
        await write_audit_event(
            db,
            identity.correlation_id,
            identity.service_id,
            "diagnostics.ami_check",
            "error",
            tenant_id=req.tenant_id,
            env=req.env,
            target_id=target.id,
            detail=str(e),
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))

    result = await diagnostic_ami_check(
        target.host, target.ami_port, target.ami_username, ami_secret
    )
    result_label = "success" if result.get("auth_ok") else "error"
    await write_audit_event(
        db,
        identity.correlation_id,
        identity.service_id,
        "diagnostics.ami_check",
        result_label,
        tenant_id=req.tenant_id,
        env=req.env,
        target_id=target.id,
    )
    await db.commit()
    return result


@router.post("/version")
async def version(
    req: TargetRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target = await _resolve_target(db, req)
    try:
        ami_secret = await fetch_secret(
            alias=target.ami_secret_alias,
            tenant_id=req.tenant_id,
            env=req.env,
            reason="diagnostics.version",
            correlation_id=req.correlation_id or identity.correlation_id,
        )
    except SecretsError as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        result = await diagnostic_version(
            target.host, target.ami_port, target.ami_username, ami_secret
        )
    except AmiError as e:
        raise HTTPException(status_code=502, detail=str(e))

    await write_audit_event(
        db,
        identity.correlation_id,
        identity.service_id,
        "diagnostics.version",
        "success",
        tenant_id=req.tenant_id,
        env=req.env,
        target_id=target.id,
    )
    await db.commit()
    return result
