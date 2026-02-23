"""
Target management API — GET/POST/PATCH /v1/targets
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.store.database import get_db
from apps.pbx_agent.store import postgres
from apps.pbx_agent.auth.identity import get_service_identity, ServiceIdentity
from apps.pbx_agent.schemas import PbxTargetCreate, PbxTargetUpdate, PbxTargetOut
from apps.pbx_agent.audit.log import write_audit_event

router = APIRouter(prefix="/v1/targets", tags=["targets"])


@router.post("", response_model=PbxTargetOut, status_code=201)
async def create_target(
    payload: PbxTargetCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    if identity.read_only:
        raise HTTPException(status_code=403, detail="Read-only service cannot create targets")
    target = await postgres.create_target(db, payload)
    await write_audit_event(db, identity.correlation_id, identity.service_id,
                            "create_target", "success",
                            tenant_id=payload.tenant_id, env=payload.env, target_id=target.id)
    await db.commit()
    await db.refresh(target)
    return PbxTargetOut.model_validate(target)


@router.get("", response_model=List[PbxTargetOut])
async def list_targets(
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    limit: int = Query(100, le=500),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    items = await postgres.list_targets(db, tenant_id=tenant_id, env=env, limit=limit)
    return [PbxTargetOut.model_validate(t) for t in items]


@router.get("/{target_id}", response_model=PbxTargetOut)
async def get_target(
    target_id: str,
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    target = await postgres.get_target(db, target_id, tenant_id, env)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return PbxTargetOut.model_validate(target)


@router.patch("/{target_id}", response_model=PbxTargetOut)
async def update_target(
    target_id: str,
    payload: PbxTargetUpdate,
    tenant_id: str = Query(...),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    if identity.read_only:
        raise HTTPException(status_code=403, detail="Read-only service cannot update targets")
    target = await postgres.update_target(db, target_id, tenant_id, env, payload)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    await write_audit_event(db, identity.correlation_id, identity.service_id,
                            "update_target", "success",
                            tenant_id=tenant_id, env=env, target_id=target_id)
    await db.commit()
    await db.refresh(target)
    return PbxTargetOut.model_validate(target)
