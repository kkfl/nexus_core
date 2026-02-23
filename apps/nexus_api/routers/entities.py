import datetime
import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireRole
from packages.shared.audit import log_audit_event
from packages.shared.db import get_db
from packages.shared.models import Entity, EntityEvent, IdempotencyKey
from packages.shared.schemas.agent_sdk import ProposedWrite
from packages.shared.sor import apply_json_merge_patch, check_idempotency, validate_proposed_write

router = APIRouter()


class EntityOut(BaseModel):
    id: str
    kind: str
    external_ref: str | None
    status: str
    data: dict | None
    version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class EntityEventOut(BaseModel):
    id: str
    entity_id: str
    actor_type: str
    actor_id: str | None
    action: str
    before: dict | None
    after: dict | None
    diff: dict | None
    correlation_id: str | None
    idempotency_key: str | None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class IdempotencyKeyOut(BaseModel):
    id: str
    key: str
    scope: str
    request_hash: str
    response: dict | None
    created_at: datetime.datetime
    expires_at: datetime.datetime

    class Config:
        from_attributes = True


class UpsertEntityRequest(BaseModel):
    kind: str
    external_ref: str | None = None
    data: dict
    idempotency_key: str


class PatchEntityRequest(BaseModel):
    patch: dict
    idempotency_key: str


@router.post("/upsert", response_model=EntityOut)
async def upsert_entity(
    req: UpsertEntityRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    # 1. Idempotency Check
    req_dict = req.model_dump()
    stored_response = await check_idempotency(db, req.idempotency_key, "entity_write", req_dict)
    if stored_response:
        return stored_response

    data_str = json.dumps(req_dict, sort_keys=True)
    req_hash = hashlib.sha256(data_str.encode()).hexdigest()

    # 2. Validate SoR Rules (Convert to ProposedWrite internally)
    pw = ProposedWrite(
        entity_kind=req.kind,
        external_ref=req.external_ref,
        action="upsert",
        patch=req.data,
        idempotency_key=req.idempotency_key,
    )
    validate_proposed_write(pw)

    # 3. Find existing or create
    if req.external_ref:
        res = await db.execute(
            select(Entity).where(Entity.kind == req.kind, Entity.external_ref == req.external_ref)
        )
        db_ent = res.scalars().first()
    else:
        db_ent = None

    correlation_id = getattr(request.state, "correlation_id", None)

    before_data = dict(db_ent.data) if db_ent and db_ent.data else None

    if db_ent:
        # Update
        merged = apply_json_merge_patch(db_ent.data or {}, req.data)
        db_ent.data = merged
        db_ent.version += 1
        action = "update"
    else:
        # Create
        db_ent = Entity(
            id=str(uuid.uuid4()),
            kind=req.kind,
            external_ref=req.external_ref,
            data=req.data,
            version=1,
        )
        db.add(db_ent)
        action = "create"
        merged = req.data

    await db.flush()  # Get ID if new

    # 4. Append Event
    db_event = EntityEvent(
        id=str(uuid.uuid4()),
        entity_id=db_ent.id,
        actor_type="user",
        actor_id=str(current_user.id),
        action=action,
        before=before_data,
        after=merged,
        diff=req.data,  # rough diff is the patch
        correlation_id=correlation_id,
        idempotency_key=req.idempotency_key,
    )
    db.add(db_event)

    log_audit_event(db, f"entity_{action}", "entity", current_user, db_ent.id)

    # 5. Record Idempotency
    resp_dict = EntityOut.model_validate(db_ent).model_dump()
    # convert datetime to isoformat for json
    for k, v in resp_dict.items():
        if isinstance(v, datetime.datetime):
            resp_dict[k] = v.isoformat()

    db_idem = IdempotencyKey(
        id=str(uuid.uuid4()),
        key=req.idempotency_key,
        scope="entity_write",
        request_hash=req_hash,
        response=resp_dict,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=7),
    )
    db.add(db_idem)

    await db.commit()
    await db.refresh(db_ent)
    return db_ent


@router.get("/", response_model=list[EntityOut])
async def list_entities(
    kind: str | None = None,
    external_ref: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
) -> Any:
    stmt = select(Entity)
    if kind:
        stmt = stmt.where(Entity.kind == kind)
    if external_ref:
        stmt = stmt.where(Entity.external_ref == external_ref)

    stmt = stmt.order_by(Entity.created_at.desc()).offset(offset).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/{entity_id}", response_model=EntityOut)
async def get_entity(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
) -> Any:
    res = await db.execute(select(Entity).where(Entity.id == entity_id))
    ent = res.scalars().first()
    if not ent:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


@router.patch("/{entity_id}", response_model=EntityOut)
async def patch_entity(
    entity_id: str,
    req: PatchEntityRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    req_dict = req.model_dump()
    stored_response = await check_idempotency(db, req.idempotency_key, "entity_write", req_dict)
    if stored_response:
        return stored_response

    data_str = json.dumps(req_dict, sort_keys=True)
    req_hash = hashlib.sha256(data_str.encode()).hexdigest()

    res = await db.execute(select(Entity).where(Entity.id == entity_id))
    db_ent = res.scalars().first()
    if not db_ent:
        raise HTTPException(status_code=404, detail="Entity not found")

    ProposedWrite(
        entity_kind=db_ent.kind,
        external_ref=db_ent.external_ref,
        action="patch",
        patch=req.patch,
        idempotency_key=req.idempotency_key,
    )
    # validate required fields might fail on patch if it assumes full object,
    # but for simplicity we rely on 'apply_json_merge_patch' to ensure final state complies.

    before_data = dict(db_ent.data) if db_ent.data else {}
    merged = apply_json_merge_patch(before_data, req.patch)

    # re-validate the merged state
    pw_merged = ProposedWrite(
        entity_kind=db_ent.kind,
        external_ref=db_ent.external_ref,
        action="patch",
        patch=merged,
        idempotency_key=req.idempotency_key,
    )
    validate_proposed_write(pw_merged)

    db_ent.data = merged
    db_ent.version += 1

    correlation_id = getattr(request.state, "correlation_id", None)

    db_event = EntityEvent(
        id=str(uuid.uuid4()),
        entity_id=db_ent.id,
        actor_type="user",
        actor_id=str(current_user.id),
        action="patch",
        before=before_data,
        after=merged,
        diff=req.patch,
        correlation_id=correlation_id,
        idempotency_key=req.idempotency_key,
    )
    db.add(db_event)

    log_audit_event(db, "entity_patch", "entity", current_user, db_ent.id)

    await db.flush()
    resp_dict = EntityOut.model_validate(db_ent).model_dump()
    for k, v in resp_dict.items():
        if isinstance(v, datetime.datetime):
            resp_dict[k] = v.isoformat()

    db_idem = IdempotencyKey(
        id=str(uuid.uuid4()),
        key=req.idempotency_key,
        scope="entity_write",
        request_hash=req_hash,
        response=resp_dict,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(days=7),
    )
    db.add(db_idem)

    await db.commit()
    await db.refresh(db_ent)
    return db_ent


@router.get("/{entity_id}/events", response_model=list[EntityEventOut])
async def list_entity_events(
    entity_id: str,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
) -> Any:
    stmt = (
        select(EntityEvent)
        .where(EntityEvent.entity_id == entity_id)
        .order_by(EntityEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/idempotency/{key}", response_model=IdempotencyKeyOut)
async def get_idempotency_key(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    res = await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == key))
    idem = res.scalars().first()
    if not idem:
        raise HTTPException(status_code=404, detail="Idempotency key not found")
    return idem
