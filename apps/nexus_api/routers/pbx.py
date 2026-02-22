import uuid
import datetime
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel

from packages.shared.db import get_db
from packages.shared.models import PbxTarget, PbxSnapshot, Secret, AuditEvent, Task, TaskRun
from apps.nexus_api.dependencies import RequireRole
from packages.shared.audit import log_audit_event

router = APIRouter()

class PbxTargetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    ami_host: str
    ami_port: int = 5038
    ami_username: str
    ami_secret: str
    ami_use_tls: bool = False
    tags: List[str] = []
    is_active: bool = True

class PbxTargetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    ami_host: Optional[str] = None
    ami_port: Optional[int] = None
    ami_username: Optional[str] = None
    ami_secret: Optional[str] = None
    ami_use_tls: Optional[bool] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None

class PbxTargetOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    ami_host: str
    ami_port: int
    ami_username: str
    ami_use_tls: bool
    tags: List[str]
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class PbxSnapshotOut(BaseModel):
    id: str
    pbx_target_id: str
    task_id: int
    status: str
    summary: Optional[dict]
    created_at: datetime.datetime

    class Config:
        from_attributes = True

@router.post("/targets", response_model=PbxTargetOut)
async def create_pbx_target(
    req: PbxTargetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"]))
) -> Any:
    from packages.shared.secrets import encrypt_secret
    
    # Store secret
    secret_id = str(uuid.uuid4())
    enc_secret = encrypt_secret(req.ami_secret)
    db_secret = Secret(
        id=secret_id,
        name=f"ami_secret_{req.name}",
        owner_type="pbx_target",
        owner_id=0, # Will be set to 0 as it uses string id instead, workaround below
        purpose="ami_password",
        ciphertext=enc_secret,
        key_version=1
    )
    db.add(db_secret)
    
    target_id = str(uuid.uuid4())
    db_target = PbxTarget(
        id=target_id,
        name=req.name,
        description=req.description,
        ami_host=req.ami_host,
        ami_port=req.ami_port,
        ami_username=req.ami_username,
        ami_secret_secret_id=secret_id,
        ami_use_tls=req.ami_use_tls,
        tags=req.tags,
        is_active=req.is_active
    )
    db.add(db_target)
    
    log_audit_event(db, "pbx_target_create", "pbx_target", current_user, target_id)
    await db.commit()
    await db.refresh(db_target)
    return db_target


@router.get("/targets", response_model=List[PbxTargetOut])
async def list_pbx_targets(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    # agents cannot call this per requirement mapped to "reader", "operator", "admin"
    res = await db.execute(select(PbxTarget))
    return res.scalars().all()


@router.get("/targets/{target_id}", response_model=PbxTargetOut)
async def get_pbx_target(
    target_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    res = await db.execute(select(PbxTarget).where(PbxTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="PBX target not found")
    return target


@router.patch("/targets/{target_id}", response_model=PbxTargetOut)
async def update_pbx_target(
    target_id: str,
    req: PbxTargetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"]))
) -> Any:
    from packages.shared.secrets import encrypt_secret
    
    res = await db.execute(select(PbxTarget).where(PbxTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="PBX target not found")
        
    for k, v in req.model_dump(exclude_unset=True).items():
        if k == "ami_secret":
            # Update secret
            sec_res = await db.execute(select(Secret).where(Secret.id == target.ami_secret_secret_id))
            secret = sec_res.scalars().first()
            if secret:
                secret.ciphertext = encrypt_secret(v)
                secret.key_version += 1
        else:
            setattr(target, k, v)
            
    log_audit_event(db, "pbx_target_update", "pbx_target", current_user, target_id)
    await db.commit()
    await db.refresh(target)
    return target


@router.post("/targets/{target_id}/test-ami")
async def test_pbx_ami(
    target_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"]))
) -> Any:
    # 1. Enqueue a task for "pbx.status" against this target
    res = await db.execute(select(PbxTarget).where(PbxTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="PBX target not found")
        
    db_task = Task(
        type="pbx.status",
        payload={"pbx_target_id": target.id},
        requested_by_id=current_user.id,
        status="queued"
    )
    db.add(db_task)
    await db.flush()
    
    db_run = TaskRun(task_id=db_task.id, attempt=1, status="dispatched")
    db.add(db_run)
    
    log_audit_event(db, "pbx_target_test", "pbx_target", current_user, target_id)
    await db.commit()
    
    # Send to RQ
    try:
        from apps.nexus_api.dependencies import get_queue
        q = get_queue()
        q.enqueue("apps.nexus_worker.jobs.dispatch_task", db_task.id)
    except Exception as e:
        print(f"Failed to enqueue task: {e}")
        
    return {"status": "dispatched", "task_id": db_task.id}


@router.get("/snapshots", response_model=List[PbxSnapshotOut])
async def list_pbx_snapshots(
    pbx_target_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    stmt = select(PbxSnapshot)
    if pbx_target_id:
        stmt = stmt.where(PbxSnapshot.pbx_target_id == pbx_target_id)
    stmt = stmt.order_by(PbxSnapshot.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/snapshots/{snapshot_id}", response_model=PbxSnapshotOut)
async def get_pbx_snapshot(
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    res = await db.execute(select(PbxSnapshot).where(PbxSnapshot.id == snapshot_id))
    snap = res.scalars().first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snap
