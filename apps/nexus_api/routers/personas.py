from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from packages.shared.db import get_db
from packages.shared.models import Persona, PersonaVersion
from packages.shared.schemas.core import PersonaCreate, PersonaOut, PersonaVersionCreate, PersonaVersionOut
from apps.nexus_api.dependencies import get_current_user, RequireRole

router = APIRouter()

@router.post("/", response_model=PersonaOut)
async def create_persona(
    persona_in: PersonaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"]))
) -> Any:
    db_persona = Persona(
        name=persona_in.name,
        description=persona_in.description,
        is_active=persona_in.is_active
    )
    db.add(db_persona)
    await db.commit()
    await db.refresh(db_persona)
    return db_persona

@router.get("/", response_model=List[PersonaOut])
async def read_personas(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    res = await db.execute(select(Persona).offset(skip).limit(limit))
    return res.scalars().all()

@router.get("/{persona_id}", response_model=PersonaOut)
async def read_persona(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    res = await db.execute(select(Persona).where(Persona.id == persona_id))
    persona = res.scalars().first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona

@router.post("/{persona_id}/versions", response_model=PersonaVersionOut)
async def create_persona_version(
    persona_id: int,
    version_in: PersonaVersionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"]))
) -> Any:
    res = await db.execute(select(Persona).where(Persona.id == persona_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail="Persona not found")
        
    db_version = PersonaVersion(
        persona_id=persona_id,
        version=version_in.version,
        system_prompt=version_in.system_prompt,
        tools_policy=version_in.tools_policy,
        meta_data=version_in.meta_data
    )
    db.add(db_version)
    await db.commit()
    await db.refresh(db_version)
    return db_version

@router.get("/{persona_id}/versions", response_model=List[PersonaVersionOut])
async def read_persona_versions(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    res = await db.execute(select(PersonaVersion).where(PersonaVersion.persona_id == persona_id))
    return res.scalars().all()
