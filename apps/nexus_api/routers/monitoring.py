import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireRole
from packages.shared.audit import log_audit_event
from packages.shared.db import get_db
from packages.shared.models import MonitoringIngest, MonitoringSource, Secret

router = APIRouter()


class MonitoringSourceCreate(BaseModel):
    name: str
    kind: str = "nagios"
    base_url: str | None = None
    auth_secret: str | None = None
    tags: list[str] = []
    is_active: bool = True


class MonitoringSourceUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    auth_secret: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class MonitoringSourceOut(BaseModel):
    id: str
    name: str
    kind: str
    base_url: str | None
    tags: list[str]
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class MonitoringIngestOut(BaseModel):
    id: str
    monitoring_source_id: str
    task_id: int
    received_at: datetime.datetime
    summary: dict | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


@router.post("/sources", response_model=MonitoringSourceOut)
async def create_monitoring_source(
    req: MonitoringSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    from packages.shared.secrets import encrypt_secret

    secret_id = None
    if req.auth_secret:
        # Store secret
        secret_id = str(uuid.uuid4())
        enc_secret = encrypt_secret(req.auth_secret)
        db_secret = Secret(
            id=secret_id,
            name=f"mon_secret_{req.name}",
            owner_type="monitoring_source",
            owner_id=0,
            purpose="auth_token",
            ciphertext=enc_secret,
            key_version=1,
        )
        db.add(db_secret)

    source_id = str(uuid.uuid4())
    db_source = MonitoringSource(
        id=source_id,
        name=req.name,
        kind=req.kind,
        base_url=req.base_url,
        auth_secret_id=secret_id,
        tags=req.tags,
        is_active=req.is_active,
    )
    db.add(db_source)

    log_audit_event(db, "monitoring_source_create", "monitoring_source", current_user, source_id)
    await db.commit()
    await db.refresh(db_source)
    return db_source


@router.get("/sources", response_model=list[MonitoringSourceOut])
async def list_monitoring_sources(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader", "agent"])),
) -> Any:
    # agents can call this to retrieve targets (if we want them to pull vs push)
    # usually payload contains exactly what they need, but sometimes they want the registry.
    res = await db.execute(select(MonitoringSource))
    return res.scalars().all()


@router.get("/sources/{source_id}", response_model=MonitoringSourceOut)
async def get_monitoring_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
) -> Any:
    res = await db.execute(select(MonitoringSource).where(MonitoringSource.id == source_id))
    source = res.scalars().first()
    if not source:
        raise HTTPException(status_code=404, detail="Monitoring source not found")
    return source


@router.patch("/sources/{source_id}", response_model=MonitoringSourceOut)
async def update_monitoring_source(
    source_id: str,
    req: MonitoringSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    from packages.shared.secrets import encrypt_secret

    res = await db.execute(select(MonitoringSource).where(MonitoringSource.id == source_id))
    source = res.scalars().first()
    if not source:
        raise HTTPException(status_code=404, detail="Monitoring source not found")

    for k, v in req.model_dump(exclude_unset=True).items():
        if k == "auth_secret":
            if source.auth_secret_id:
                sec_res = await db.execute(select(Secret).where(Secret.id == source.auth_secret_id))
                secret = sec_res.scalars().first()
                if secret:
                    secret.ciphertext = encrypt_secret(v)
                    secret.key_version += 1
            else:
                new_sec_id = str(uuid.uuid4())
                enc_secret = encrypt_secret(v)
                db_secret = Secret(
                    id=new_sec_id,
                    name=f"mon_secret_{source.name}",
                    owner_type="monitoring_source",
                    owner_id=0,
                    purpose="auth_token",
                    ciphertext=enc_secret,
                    key_version=1,
                )
                db.add(db_secret)
                source.auth_secret_id = new_sec_id
        else:
            setattr(source, k, v)

    log_audit_event(db, "monitoring_source_update", "monitoring_source", current_user, source_id)
    await db.commit()
    await db.refresh(source)
    return source


@router.get("/ingests", response_model=list[MonitoringIngestOut])
async def list_monitoring_ingests(
    monitoring_source_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
) -> Any:
    stmt = select(MonitoringIngest)
    if monitoring_source_id:
        stmt = stmt.where(MonitoringIngest.monitoring_source_id == monitoring_source_id)
    stmt = stmt.order_by(MonitoringIngest.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/ingests/{ingest_id}", response_model=MonitoringIngestOut)
async def get_monitoring_ingest(
    ingest_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
) -> Any:
    res = await db.execute(select(MonitoringIngest).where(MonitoringIngest.id == ingest_id))
    ing = res.scalars().first()
    if not ing:
        raise HTTPException(status_code=404, detail="Ingest not found")
    return ing
