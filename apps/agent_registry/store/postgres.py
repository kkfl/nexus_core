"""
PostgreSQL storage backend for agent_registry.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.agent_registry.models import (
    RegistryAgent,
    RegistryAuditEvent,
    RegistryCapability,
    RegistryDeployment,
)
from apps.agent_registry.schemas import (
    AgentCreate,
    AgentUpdate,
    CapabilitySpec,
    DeploymentCreate,
    DeploymentUpdate,
)

_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://nexus:nexus_pass@localhost:5432/nexus_core"
)
_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=5, max_overflow=10)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


async def list_agents(db: AsyncSession) -> list[RegistryAgent]:
    result = await db.execute(select(RegistryAgent).order_by(RegistryAgent.name))
    return list(result.scalars().all())


async def get_agent_by_name(db: AsyncSession, name: str) -> RegistryAgent | None:
    result = await db.execute(select(RegistryAgent).where(RegistryAgent.name == name))
    return result.scalar_one_or_none()


async def get_agent_by_id(db: AsyncSession, agent_id: str) -> RegistryAgent | None:
    result = await db.execute(select(RegistryAgent).where(RegistryAgent.id == agent_id))
    return result.scalar_one_or_none()


async def create_agent(db: AsyncSession, payload: AgentCreate) -> RegistryAgent:
    agent = RegistryAgent(**payload.model_dump())
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def update_agent(
    db: AsyncSession, agent: RegistryAgent, payload: AgentUpdate
) -> RegistryAgent:
    update_data = payload.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(agent, key, value)
        await db.commit()
        await db.refresh(agent)
    return agent


# ---------------------------------------------------------------------------
# Deployments
# ---------------------------------------------------------------------------


async def list_deployments(
    db: AsyncSession,
    tenant_id: str | None = None,
    env: str | None = None,
    agent_id: str | None = None,
) -> list[RegistryDeployment]:
    stmt = select(RegistryDeployment).order_by(RegistryDeployment.created_at.desc())
    if tenant_id:
        stmt = stmt.where(RegistryDeployment.tenant_id == tenant_id)
    if env:
        stmt = stmt.where(RegistryDeployment.env == env)
    if agent_id:
        stmt = stmt.where(RegistryDeployment.agent_id == agent_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_deployment(db: AsyncSession, deployment_id: str) -> RegistryDeployment | None:
    result = await db.execute(
        select(RegistryDeployment).where(RegistryDeployment.id == deployment_id)
    )
    return result.scalar_one_or_none()


async def get_deployment_by_agent_and_env(
    db: AsyncSession, agent_id: str, tenant_id: str | None, env: str
) -> RegistryDeployment | None:
    stmt = (
        select(RegistryDeployment)
        .where(RegistryDeployment.agent_id == agent_id)
        .where(RegistryDeployment.env == env)
    )
    if tenant_id:
        stmt = stmt.where(RegistryDeployment.tenant_id == tenant_id)
    else:
        stmt = stmt.where(RegistryDeployment.tenant_id.is_(None))
    result = await db.execute(stmt)
    # Return highest precedence or first if there are conflicts
    return result.scalars().first()


async def create_deployment(db: AsyncSession, payload: DeploymentCreate) -> RegistryDeployment:
    dep = RegistryDeployment(**payload.model_dump())
    db.add(dep)
    await db.commit()
    await db.refresh(dep)
    return dep


async def update_deployment(
    db: AsyncSession, dep: RegistryDeployment, payload: DeploymentUpdate
) -> RegistryDeployment:
    update_data = payload.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(dep, key, value)
        await db.commit()
        await db.refresh(dep)
    return dep


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


async def override_capabilities(
    db: AsyncSession, agent_id: str, capabilities: list[CapabilitySpec]
) -> None:
    """Overwrites all capabilities for a given agent with the provided slice."""
    # 1. Delete existing capabilities for this agent
    await db.execute(delete(RegistryCapability).where(RegistryCapability.agent_id == agent_id))

    # 2. Insert new
    if capabilities:
        new_caps = [RegistryCapability(agent_id=agent_id, **c.model_dump()) for c in capabilities]
        db.add_all(new_caps)

    await db.commit()


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


async def log_audit(
    db: AsyncSession,
    correlation_id: str,
    service_id: str,
    action: str,
    result: str,
    tenant_id: str | None = None,
    env: str | None = None,
    detail: str | None = None,
) -> None:
    event = RegistryAuditEvent(
        correlation_id=correlation_id,
        service_id=service_id,
        tenant_id=tenant_id,
        env=env,
        action=action,
        result=result,
        detail=detail,
    )
    db.add(event)
    await db.commit()
