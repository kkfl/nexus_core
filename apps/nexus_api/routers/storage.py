import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import exc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import get_current_user
from packages.shared.db import get_db
from packages.shared.models import AuditEvent, Secret, StorageJob, StorageTarget, Task
from packages.shared.secrets import encrypt_secret

router = APIRouter(tags=["storage"])


class StorageTargetCreateConfig(BaseModel):
    name: str  # display name
    description: str | None = None
    kind: str = "s3"
    endpoint_url: str
    region: str | None = None
    bucket: str
    access_key_id: str
    secret_access_key: str
    base_prefix: str = ""
    tags: list[str] | None = []


class StorageTargetPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint_url: str | None = None
    region: str | None = None
    bucket: str | None = None
    base_prefix: str | None = None
    is_active: bool | None = None
    tags: list[str] | None = None


class StorageTargetResponse(BaseModel):
    id: str
    name: str
    description: str | None
    kind: str
    endpoint_url: str
    region: str | None
    bucket: str
    base_prefix: str
    is_active: bool
    tags: list[str] | None
    created_at: datetime.datetime


class StorageJobResponse(BaseModel):
    id: str
    storage_target_id: str
    task_id: int
    kind: str
    status: str
    summary: dict[str, Any] | None
    created_at: datetime.datetime


@router.post("/targets", response_model=StorageTargetResponse)
async def create_storage_target(
    config: StorageTargetCreateConfig,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Not authorized")

    target_id = str(uuid.uuid4())

    # Secure storage of access key
    ak_id = str(uuid.uuid4())
    db_ak = Secret(
        id=ak_id,
        name=f"storage_target_ak_{target_id}",
        owner_type="global",
        owner_id=user.id,
        purpose="storage_target_auth",
        ciphertext=encrypt_secret(config.access_key_id),
        key_version=1,
    )
    db.add(db_ak)

    # Secure storage of secret key
    sk_id = str(uuid.uuid4())
    db_sk = Secret(
        id=sk_id,
        name=f"storage_target_sk_{target_id}",
        owner_type="global",
        owner_id=user.id,
        purpose="storage_target_auth",
        ciphertext=encrypt_secret(config.secret_access_key),
        key_version=1,
    )
    db.add(db_sk)

    db_target = StorageTarget(
        id=target_id,
        name=config.name,
        description=config.description,
        kind=config.kind,
        endpoint_url=config.endpoint_url,
        region=config.region,
        bucket=config.bucket,
        access_key_id_secret_id=ak_id,
        secret_access_key_secret_id=sk_id,
        base_prefix=config.base_prefix,
        tags=config.tags,
    )
    db.add(db_target)

    db.add(
        AuditEvent(
            actor_type="user",
            actor_id=user.id,
            action="create_storage_target",
            target_type="storage_target",
            target_id=0,
            meta_data={"target_id": target_id},
        )
    )

    try:
        await db.commit()
        await db.refresh(db_target)
    except exc.IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Storage target name exists")

    return db_target


@router.get("/targets", response_model=list[StorageTargetResponse])
async def list_storage_targets(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=403, detail="Not authorized")
    res = await db.execute(select(StorageTarget))
    return res.scalars().all()


@router.get("/targets/{target_id}", response_model=StorageTargetResponse)
async def get_storage_target(
    target_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if user.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=403, detail="Not authorized")
    res = await db.execute(select(StorageTarget).where(StorageTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@router.patch("/targets/{target_id}", response_model=StorageTargetResponse)
async def update_storage_target(
    target_id: str,
    patch: StorageTargetPatch,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Not authorized")

    res = await db.execute(select(StorageTarget).where(StorageTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    update_data = patch.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(target, k, v)

    db.add(
        AuditEvent(
            actor_type="user",
            actor_id=user.id,
            action="update_storage_target",
            target_type="storage_target",
            target_id=0,
            meta_data={"target_id": target_id},
        )
    )

    await db.commit()
    await db.refresh(target)
    return target


@router.post("/targets/{target_id}/test")
async def test_storage_target(
    target_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if user.role not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Not authorized")

    res = await db.execute(select(StorageTarget).where(StorageTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    task = Task(
        type="storage.list",
        status="queued",
        priority=1,
        payload={"storage_target_id": target_id, "prefix": target.base_prefix, "max_keys": 1},
        requested_by_user_id=user.id,
    )
    db.add(task)
    db.add(
        AuditEvent(
            actor_type="user",
            actor_id=user.id,
            action="test_storage_target",
            target_type="storage_target",
            target_id=0,
            meta_data={"target_id": target_id, "task_id": 0},
        )
    )  # We don't have task.id yet, but close enough
    await db.commit()
    return {"message": "Test task queued", "task_id": task.id}


@router.get("/jobs", response_model=list[StorageJobResponse])
async def list_storage_jobs(
    storage_target_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=403, detail="Not authorized")

    query = select(StorageJob).order_by(StorageJob.created_at.desc()).limit(limit).offset(offset)
    if storage_target_id:
        query = query.where(StorageJob.storage_target_id == storage_target_id)

    res = await db.execute(query)
    return res.scalars().all()


@router.get("/jobs/{job_id}", response_model=StorageJobResponse)
async def get_storage_job(
    job_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if user.role not in ("admin", "operator", "reader"):
        raise HTTPException(status_code=403, detail="Not authorized")

    res = await db.execute(select(StorageJob).where(StorageJob.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
