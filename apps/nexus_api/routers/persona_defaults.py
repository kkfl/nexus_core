from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from packages.shared.db import get_db
from packages.shared.models import PersonaDefault
from packages.shared.schemas.core import PersonaDefaultCreate, PersonaDefaultOut, PersonaDefaultUpdate
from apps.nexus_api.dependencies import get_current_user, RequireRole

router = APIRouter()

@router.post("/", response_model=PersonaDefaultOut)
async def create_persona_default(
    default_in: PersonaDefaultCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"]))
) -> Any:
    db_default = PersonaDefault(
        scope_type=default_in.scope_type,
        scope_value=default_in.scope_value,
        persona_version_id=default_in.persona_version_id,
        is_active=default_in.is_active
    )
    db.add(db_default)
    await db.commit()
    await db.refresh(db_default)
    return db_default

@router.get("/", response_model=List[PersonaDefaultOut])
async def read_persona_defaults(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"]))
) -> Any:
    res = await db.execute(select(PersonaDefault).offset(skip).limit(limit))
    return res.scalars().all()

@router.patch("/{default_id}", response_model=PersonaDefaultOut)
async def update_persona_default(
    default_id: int,
    default_in: PersonaDefaultUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"]))
) -> Any:
    res = await db.execute(select(PersonaDefault).where(PersonaDefault.id == default_id))
    default = res.scalars().first()
    if not default:
        raise HTTPException(status_code=404, detail="PersonaDefault not found")
        
    update_data = default_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(default, field, value)
        
    await db.commit()
    await db.refresh(default)
    return default
