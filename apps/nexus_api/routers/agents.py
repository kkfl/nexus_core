import secrets
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from apps.nexus_api.dependencies import (
    RequireRole,
    get_current_agent_by_key,
)
from packages.shared.audit import log_audit_event
from packages.shared.db import get_db
from packages.shared.models import Agent, AgentCheckin, Secret
from packages.shared.schemas.core import (
    AgentCheckinCreate,
    AgentCheckinOut,
    AgentCreate,
    AgentOut,
    AgentUpdate,
)
from packages.shared.secrets import encrypt_secret

router = APIRouter()


@router.post("/", response_model=dict)
async def create_agent(
    agent_in: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    db_agent = Agent(
        name=agent_in.name,
        base_url=agent_in.base_url,
        auth_type=agent_in.auth_type,
        capabilities=agent_in.capabilities,
        max_concurrency=agent_in.max_concurrency,
        timeout_seconds=agent_in.timeout_seconds,
    )
    db.add(db_agent)
    await db.flush()  # assign db_agent.id before the secret block below

    raw_key = None
    if agent_in.auth_type == "api_key":
        raw_key = secrets.token_urlsafe(32)
        ciphertext = encrypt_secret(raw_key)

        db_secret = Secret(
            id=str(uuid.uuid4()),
            name=f"agent_outbound_key_{db_agent.id}",
            owner_type="agent",
            owner_id=db_agent.id,
            purpose="agent_outbound_key",
            ciphertext=ciphertext,
            key_version=1,
        )
        db.add(db_secret)

    log_audit_event(db, "agent_create", "agent", current_user, str(db_agent.id))
    await db.commit()
    await db.refresh(db_agent)

    result = AgentOut.model_validate(db_agent).model_dump()
    if raw_key:
        result["raw_key"] = raw_key
    return result


@router.get("/", response_model=list[AgentOut])
async def read_agents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
) -> Any:
    result = await db.execute(select(Agent).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{agent_id}", response_model=AgentOut)
async def read_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator", "reader"])),
) -> Any:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: int,
    agent_in: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = agent_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    log_audit_event(db, "agent_update", "agent", current_user, str(agent.id))
    await db.commit()
    await db.refresh(agent)
    return agent


@router.post("/{agent_id}/ping")
async def ping_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(RequireRole(["admin", "operator"])),
) -> Any:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{agent.base_url}/health")
            resp.raise_for_status()
            return {"status": "ok", "latency_ms": resp.elapsed.total_seconds() * 1000}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ping failed: {str(e)}")


@router.post("/{agent_id}/checkin", response_model=AgentCheckinOut)
async def checkin_agent(
    agent_id: int,
    checkin_in: AgentCheckinCreate,
    db: AsyncSession = Depends(get_db),
    # Require agent level auth to perform checkin
    current_agent: Agent = Depends(get_current_agent_by_key),
) -> Any:
    # Verify auth
    if current_agent.id != agent_id:
        raise HTTPException(status_code=403, detail="Not authorized to checkin for this agent")

    # Update agent last_seen_at & status
    import datetime

    current_agent.last_seen_at = datetime.datetime.now(datetime.UTC)
    current_agent.status = checkin_in.status
    db.add(current_agent)

    db_checkin = AgentCheckin(
        agent_id=agent_id,
        status=checkin_in.status,
        meta_data=checkin_in.meta_data,
    )
    db.add(db_checkin)

    await db.commit()
    await db.refresh(db_checkin)
    return db_checkin
