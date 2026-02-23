"""
Capabilities router — POST /v1/capabilities
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.agent_registry.auth.identity import ServiceIdentity, get_service_identity
from apps.agent_registry.schemas import CapabilitiesCreate
from apps.agent_registry.store import postgres as store

router = APIRouter(prefix="/v1/capabilities", tags=["capabilities"])


@router.post("", status_code=status.HTTP_200_OK)
async def upsert_capabilities(
    payload: CapabilitiesCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
):
    """
    Overwrites the specified agent's capabilities with the provided list.
    Called by Nexus during startup discovery.
    """
    agent = await store.get_agent_by_id(db, payload.agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent ID '{payload.agent_id}' not found. Cannot register capabilities."
        )

    await store.override_capabilities(db, agent.id, payload.capabilities)

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        action="override_capabilities",
        result="success",
        detail=f"Overwrote capabilities for agent {agent.name} with {len(payload.capabilities)} specs"
    )

    return {"status": "success", "message": f"Registered {len(payload.capabilities)} capabilities for agent {agent.name}."}
