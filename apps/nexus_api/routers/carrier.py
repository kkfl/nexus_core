from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import exc
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid
import datetime

from packages.shared.db import get_db
from packages.shared.models import CarrierTarget, CarrierSnapshot, Secret, AuditEvent, Task
from apps.nexus_api.dependencies import get_current_user
from packages.shared.secrets import encrypt_secret

router = APIRouter(prefix="/carrier", tags=["carrier"])

class CarrierTargetCreate(BaseModel):
    name: str # display name
    provider: str = "mock"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    tags: Optional[List[str]] = []
    
class CarrierTargetPatch(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None
    tags: Optional[List[str]] = None

class CarrierTargetResponse(BaseModel):
    id: str
    name: str
    provider: str
    base_url: Optional[str]
    is_active: bool
    tags: Optional[List[str]]
    created_at: datetime.datetime

class CarrierSnapshotResponse(BaseModel):
    id: str
    carrier_target_id: str
    task_id: int
    status: str
    summary: Optional[Dict[str, Any]]
    created_at: datetime.datetime

@router.post("/targets", response_model=CarrierTargetResponse)
async def create_carrier_target(
    config: CarrierTargetCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user.role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    target_id = str(uuid.uuid4())
    
    ak_id = None
    if config.api_key:
        ak_id = str(uuid.uuid4())
        db_ak = Secret(
            id=ak_id,
            name=f"carrier_target_ak_{target_id}",
            owner_type="global",
            owner_id=user.id,
            purpose="carrier_target_auth",
            ciphertext=encrypt_secret(config.api_key),
            key_version=1
        )
        db.add(db_ak)
    
    sk_id = None
    if config.api_secret:
        sk_id = str(uuid.uuid4())
        db_sk = Secret(
            id=sk_id,
            name=f"carrier_target_sk_{target_id}",
            owner_type="global",
            owner_id=user.id,
            purpose="carrier_target_auth",
            ciphertext=encrypt_secret(config.api_secret),
            key_version=1
        )
        db.add(db_sk)
    
    db_target = CarrierTarget(
        id=target_id,
        name=config.name,
        provider=config.provider,
        base_url=config.base_url,
        api_key_secret_id=ak_id,
        api_secret_secret_id=sk_id,
        tags=config.tags
    )
    db.add(db_target)
    
    db.add(AuditEvent(actor_type="user", actor_id=user.id, action="create_carrier_target", target_type="carrier_target", target_id=0, meta_data={"target_id": target_id}))
    
    try:
        await db.commit()
        await db.refresh(db_target)
    except exc.IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Carrier target name exists")
        
    return db_target

@router.get("/targets", response_model=List[CarrierTargetResponse])
async def list_carrier_targets(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=403, detail="Not authorized")
    res = await db.execute(select(CarrierTarget))
    return res.scalars().all()

@router.get("/targets/{target_id}", response_model=CarrierTargetResponse)
async def get_carrier_target(target_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=403, detail="Not authorized")
    res = await db.execute(select(CarrierTarget).where(CarrierTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target

@router.patch("/targets/{target_id}", response_model=CarrierTargetResponse)
async def update_carrier_target(
    target_id: str,
    patch: CarrierTargetPatch,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user.role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Not authorized")
        
    res = await db.execute(select(CarrierTarget).where(CarrierTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
        
    update_data = patch.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(target, k, v)
        
    db.add(AuditEvent(actor_type="user", actor_id=user.id, action="update_carrier_target", target_type="carrier_target", target_id=0, meta_data={"target_id": target_id}))
    
    await db.commit()
    await db.refresh(target)
    return target

@router.post("/targets/{target_id}/test")
async def test_carrier_target(
    target_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user.role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Not authorized")

    res = await db.execute(select(CarrierTarget).where(CarrierTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    task = Task(
        type="carrier.account.status",
        status="queued",
        priority=1,
        payload={
            "carrier_target_id": target_id
        },
        requested_by_user_id=user.id
    )
    db.add(task)
    db.add(AuditEvent(actor_type="user", actor_id=user.id, action="test_carrier_target", target_type="carrier_target", target_id=0, meta_data={"target_id": target_id, "task_id": 0}))
    await db.commit()
    return {"message": "Test task queued", "task_id": task.id}

@router.get("/snapshots", response_model=List[CarrierSnapshotResponse])
async def list_carrier_snapshots(
    carrier_target_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=403, detail="Not authorized")

    query = select(CarrierSnapshot).order_by(CarrierSnapshot.created_at.desc()).limit(limit).offset(offset)
    if carrier_target_id:
        query = query.where(CarrierSnapshot.carrier_target_id == carrier_target_id)
        
    res = await db.execute(query)
    return res.scalars().all()

@router.get("/snapshots/{snapshot_id}", response_model=CarrierSnapshotResponse)
async def get_carrier_snapshot(
    snapshot_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if user.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=403, detail="Not authorized")

    res = await db.execute(select(CarrierSnapshot).where(CarrierSnapshot.id == snapshot_id))
    snapshot = res.scalars().first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot
