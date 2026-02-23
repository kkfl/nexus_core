"""Policies router — admin-only CRUD for vault access policies."""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.secrets_agent.dependencies import ServiceIdentity, get_vault_db, require_admin
from apps.secrets_agent.models import VaultPolicy
from apps.secrets_agent.schemas import PolicyCreate, PolicyOut

router = APIRouter(prefix="/v1/policies", tags=["policies"])


@router.post("", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: PolicyCreate,
    _: ServiceIdentity = Depends(require_admin),
    db: AsyncSession = Depends(get_vault_db),
) -> PolicyOut:
    policy = VaultPolicy(
        id=str(uuid.uuid4()),
        name=payload.name,
        service_id=payload.service_id,
        alias_pattern=payload.alias_pattern,
        tenant_id=payload.tenant_id,
        env=payload.env,
        actions=payload.actions,
        priority=payload.priority,
        is_active=True,
    )
    db.add(policy)
    await db.flush()
    return PolicyOut.model_validate(policy)


@router.get("", response_model=List[PolicyOut])
async def list_policies(
    _: ServiceIdentity = Depends(require_admin),
    db: AsyncSession = Depends(get_vault_db),
) -> List[PolicyOut]:
    result = await db.execute(select(VaultPolicy).order_by(VaultPolicy.priority.desc()))
    return [PolicyOut.model_validate(p) for p in result.scalars().all()]


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    _: ServiceIdentity = Depends(require_admin),
    db: AsyncSession = Depends(get_vault_db),
) -> Response:
    result = await db.execute(select(VaultPolicy).where(VaultPolicy.id == policy_id))
    policy = result.scalars().first()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found.")
    policy.is_active = False
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
