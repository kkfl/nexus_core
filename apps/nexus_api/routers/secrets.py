import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import RequireRole
from packages.shared.db import get_db
from packages.shared.models import Secret
from packages.shared.secrets import encrypt_secret

router = APIRouter()


class SecretCreate(BaseModel):
    name: str
    owner_type: str  # 'global', 'agent', 'user'
    owner_id: int | None = None
    purpose: str
    plaintext: str
    meta_data: dict | None = None


class SecretOut(BaseModel):
    id: str
    name: str
    owner_type: str
    owner_id: int | None
    purpose: str
    key_version: int
    meta_data: dict | None

    class Config:
        from_attributes = True


class SecretUpdate(BaseModel):
    plaintext: str
    meta_data: dict | None = None


@router.post("/", response_model=SecretOut)
async def create_secret(
    secret_in: SecretCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    # Check if exists
    res = await db.execute(select(Secret).where(Secret.name == secret_in.name))
    if res.scalars().first():
        raise HTTPException(status_code=400, detail="Secret with this name already exists")

    try:
        ciphertext = encrypt_secret(secret_in.plaintext)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    db_secret = Secret(
        id=str(uuid.uuid4()),
        name=secret_in.name,
        owner_type=secret_in.owner_type,
        owner_id=secret_in.owner_id,
        purpose=secret_in.purpose,
        ciphertext=ciphertext,
        key_version=1,
        meta_data=secret_in.meta_data,
    )
    db.add(db_secret)
    await db.commit()
    await db.refresh(db_secret)
    return db_secret


@router.get("/", response_model=list[SecretOut])
async def read_secrets(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    # Metadata only, never the plaintext
    res = await db.execute(select(Secret).offset(skip).limit(limit))
    return res.scalars().all()


@router.patch("/{secret_id}", response_model=SecretOut)
async def update_secret(
    secret_id: str,
    secret_in: SecretUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    res = await db.execute(select(Secret).where(Secret.id == secret_id))
    db_secret = res.scalars().first()
    if not db_secret:
        raise HTTPException(status_code=404, detail="Secret not found")

    try:
        ciphertext = encrypt_secret(secret_in.plaintext)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    db_secret.ciphertext = ciphertext
    db_secret.key_version += 1
    if secret_in.meta_data is not None:
        db_secret.meta_data = secret_in.meta_data

    await db.commit()
    await db.refresh(db_secret)
    return db_secret


@router.delete("/{secret_id}")
async def delete_secret(
    secret_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    res = await db.execute(select(Secret).where(Secret.id == secret_id))
    db_secret = res.scalars().first()
    if not db_secret:
        raise HTTPException(status_code=404, detail="Secret not found")

    await db.delete(db_secret)
    await db.commit()
    return {"status": "deleted"}
