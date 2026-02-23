"""
Deployments router — GET /v1/deployments, POST /v1/deployments, PATCH /v1/deployments/{id}
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.agent_registry.auth.identity import ServiceIdentity, get_service_identity
from apps.agent_registry.schemas import DeploymentCreate, DeploymentOut, DeploymentUpdate
from apps.agent_registry.store import postgres as store

router = APIRouter(prefix="/v1/deployments", tags=["deployments"])


@router.get("", response_model=List[DeploymentOut])
async def list_deployments(
    tenant_id: Optional[str] = Query(None),
    env: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> List[DeploymentOut]:
    """List deployments, optionally filtered by tenant, env, and agent."""
    deps = await store.list_deployments(db, tenant_id=tenant_id, env=env, agent_id=agent_id)
    return [DeploymentOut.model_validate(d) for d in deps]


@router.get("/{deployment_id}", response_model=DeploymentOut)
async def get_deployment(
    deployment_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> DeploymentOut:
    """Get a deployment by ID."""
    dep = await store.get_deployment(db, deployment_id)
    if not dep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found."
        )
    return DeploymentOut.model_validate(dep)


@router.post("", response_model=DeploymentOut, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    payload: DeploymentCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> DeploymentOut:
    """Register a new deployment for an agent."""
    agent = await store.get_agent_by_id(db, payload.agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent ID '{payload.agent_id}' not found. Cannot create deployment."
        )

    # Check for conflicts (no strict unique constraint across tenant+env in DB to allow multiple replicas, 
    # but we will conceptually just add the deployment record).
    dep = await store.create_deployment(db, payload)

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        tenant_id=payload.tenant_id,
        env=payload.env,
        action="create_deployment",
        result="success",
        detail=f"Created deployment for agent {agent.name}"
    )

    return DeploymentOut.model_validate(dep)


@router.patch("/{deployment_id}", response_model=DeploymentOut)
async def patch_deployment(
    deployment_id: str,
    payload: DeploymentUpdate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> DeploymentOut:
    """Update an existing deployment."""
    dep = await store.get_deployment(db, deployment_id)
    if not dep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found."
        )

    updated = await store.update_deployment(db, dep, payload)

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        tenant_id=updated.tenant_id,
        env=updated.env,
        action="update_deployment",
        result="success",
        detail=f"Updated deployment {deployment_id}"
    )

    return DeploymentOut.model_validate(updated)
