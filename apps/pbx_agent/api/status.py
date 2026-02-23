"""
Status API — POST /v1/status/{metric}
Real-time read-only AMI status queries.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.store.database import get_db
from apps.pbx_agent.store import postgres
from apps.pbx_agent.auth.identity import get_service_identity, ServiceIdentity
from apps.pbx_agent.schemas import TargetRequest
from apps.pbx_agent.client.secrets import fetch_secret, SecretsError
from apps.pbx_agent.ops.status import status_peers, status_registrations, status_channels, status_uptime
from apps.pbx_agent.adapters.ami import AmiError

router = APIRouter(prefix="/v1/status", tags=["status"])


async def _get_target_and_secret(db, req: TargetRequest, reason: str, correlation_id: str):
    target = await postgres.get_target(db, req.pbx_target_id, req.tenant_id, req.env)
    if not target:
        raise HTTPException(status_code=404, detail=f"Target '{req.pbx_target_id}' not found")
    try:
        secret = await fetch_secret(
            alias=target.ami_secret_alias,
            tenant_id=req.tenant_id,
            env=req.env,
            reason=reason,
            correlation_id=correlation_id,
        )
    except SecretsError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return target, secret


@router.post("/peers")
async def get_peers(
    req: TargetRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target, secret = await _get_target_and_secret(db, req, "status.peers", identity.correlation_id)
    try:
        return await status_peers(target.host, target.ami_port, target.ami_username, secret)
    except AmiError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/registrations")
async def get_registrations(
    req: TargetRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target, secret = await _get_target_and_secret(db, req, "status.registrations", identity.correlation_id)
    try:
        return await status_registrations(target.host, target.ami_port, target.ami_username, secret)
    except AmiError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/channels")
async def get_channels(
    req: TargetRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target, secret = await _get_target_and_secret(db, req, "status.channels", identity.correlation_id)
    try:
        return await status_channels(target.host, target.ami_port, target.ami_username, secret)
    except AmiError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/uptime")
async def get_uptime(
    req: TargetRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target, secret = await _get_target_and_secret(db, req, "status.uptime", identity.correlation_id)
    try:
        return await status_uptime(target.host, target.ami_port, target.ami_username, secret)
    except AmiError as e:
        raise HTTPException(status_code=502, detail=str(e))
