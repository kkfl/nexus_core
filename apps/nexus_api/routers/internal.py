from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.routers.pbx import PbxTargetOut
from packages.shared.db import get_db
from packages.shared.models import (
    Agent,
    ApiKey,
    AuditEvent,
    CarrierTarget,
    PbxTarget,
    Secret,
    StorageTarget,
)
from packages.shared.secrets import decrypt_secret


class StorageTargetInternalOut(BaseModel):
    id: str
    name: str
    kind: str
    endpoint_url: str
    region: str | None
    bucket: str
    access_key_id_secret_id: str
    secret_access_key_secret_id: str
    base_prefix: str


class CarrierTargetInternalOut(BaseModel):
    id: str
    name: str
    provider: str
    base_url: str | None
    api_key_secret_id: str | None
    api_secret_secret_id: str | None


router = APIRouter()

api_key_header = APIKeyHeader(name="X-Nexus-Internal", auto_error=True)


async def _get_internal_agent(
    api_key: str = Security(api_key_header), db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(ApiKey).where(ApiKey.key == api_key, ApiKey.is_active is True))
    key_record = res.scalars().first()
    if not key_record or key_record.owner_type != "agent":
        raise HTTPException(status_code=401, detail="Invalid or unauthorized internal key")

    res_agent = await db.execute(select(Agent).where(Agent.id == key_record.owner_id))
    agent = res_agent.scalars().first()
    if not agent:
        raise HTTPException(status_code=401, detail="Agent not found")

    return agent


class DecryptRequest(BaseModel):
    secret_id: str


@router.post("/secrets/decrypt")
async def decrypt_internal_secret(
    req: DecryptRequest,
    current_agent: Agent = Depends(_get_internal_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    # Fetch secret
    sec_res = await db.execute(select(Secret).where(Secret.id == req.secret_id))
    secret = sec_res.scalars().first()

    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")

    # Authorization checks:
    # Option 1: secret belongs to this specific agent
    authorized = False
    if (
        secret.owner_type == "agent"
        and secret.owner_id == current_agent.id
        or secret.owner_type == "pbx_target"
        or secret.purpose == "storage_target_auth"
        or secret.purpose == "carrier_target_auth"
    ):
        authorized = True

    if not authorized:
        # Audit denial
        db.add(
            AuditEvent(
                actor_type="agent",
                actor_id=current_agent.id,
                action="secret_decrypt_denied",
                target_type="secret",
                target_id=0,
                meta_data={"secret_id": req.secret_id},
            )
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Unauthorized to decrypt this secret")

    # Decrypt
    try:
        plaintext = decrypt_secret(secret.ciphertext)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt secret")

    db.add(
        AuditEvent(
            actor_type="agent",
            actor_id=current_agent.id,
            action="secret_decrypt",
            target_type="secret",
            target_id=0,
            meta_data={"secret_id": req.secret_id},
        )
    )
    await db.commit()

    return {"value": plaintext}


@router.get("/pbx/targets/{target_id}", response_model=PbxTargetOut)
async def get_internal_pbx_target(
    target_id: str,
    current_agent: Agent = Depends(_get_internal_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    # Allow agents to read PBX Target metadata to connect to AMI
    res = await db.execute(select(PbxTarget).where(PbxTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="PBX target not found")

    return target


@router.get("/storage/targets/{target_id}", response_model=StorageTargetInternalOut)
async def get_internal_storage_target(
    target_id: str,
    current_agent: Agent = Depends(_get_internal_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    # Allow agents to read Storage Target metadata and secret IDs
    res = await db.execute(select(StorageTarget).where(StorageTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Storage target not found")

    return target


@router.get("/carrier/targets/{target_id}", response_model=CarrierTargetInternalOut)
async def get_internal_carrier_target(
    target_id: str,
    current_agent: Agent = Depends(_get_internal_agent),
    db: AsyncSession = Depends(get_db),
) -> Any:
    # Allow agents to read Carrier Target metadata and secret IDs
    res = await db.execute(select(CarrierTarget).where(CarrierTarget.id == target_id))
    target = res.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Carrier target not found")

    return target
