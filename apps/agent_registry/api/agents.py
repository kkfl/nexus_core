"""
Agents router — GET /v1/agents, GET /v1/agents/{name}, POST /v1/agents, PATCH /v1/agents/{name}
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.agent_registry.auth.identity import ServiceIdentity, get_service_identity
from apps.agent_registry.schemas import AgentCreate, AgentOut, AgentUpdate
from apps.agent_registry.store import postgres as store

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
async def list_agents(
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> list[AgentOut]:
    """List all registered agents."""
    agents = await store.list_agents(db)
    return [AgentOut.model_validate(a) for a in agents]


@router.get("/{name}", response_model=AgentOut)
async def get_agent(
    name: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> AgentOut:
    """Get a specific agent by its unique name."""
    agent = await store.get_agent_by_name(db, name)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{name}' not found.",
        )
    return AgentOut.model_validate(agent)


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> AgentOut:
    """Register a new agent."""
    existing = await store.get_agent_by_name(db, payload.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{payload.name}' already exists.",
        )

    agent = await store.create_agent(db, payload)

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        action="create_agent",
        result="success",
        detail=f"Created agent {payload.name}",
    )

    return AgentOut.model_validate(agent)


@router.patch("/{name}", response_model=AgentOut)
async def patch_agent(
    name: str,
    payload: AgentUpdate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> AgentOut:
    """Update an existing agent."""
    agent = await store.get_agent_by_name(db, name)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{name}' not found.",
        )

    updated = await store.update_agent(db, agent, payload)

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        action="update_agent",
        result="success",
        detail=f"Updated agent {name}",
    )

    return AgentOut.model_validate(updated)
