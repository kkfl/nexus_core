"""
Targets REST API
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.monitoring_agent.engine.sync import sync_from_registry
from apps.monitoring_agent.store.postgres import get_db, get_targets

# from apps.monitoring_agent.auth.identity import get_service_identity, ServiceIdentity

router = APIRouter(prefix="/v1/targets", tags=["targets"])


@router.get("")
async def list_targets(
    tenant_id: str | None = Query(None),
    env: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    targets = await get_targets(db, tenant_id, env)
    return [
        {
            "id": t.id,
            "tenant_id": t.tenant_id,
            "env": t.env,
            "agent_name": t.agent_name,
            "deployment_id": t.deployment_id,
            "base_url": t.base_url,
            "enabled": t.enabled,
            "tags": t.tags,
        }
        for t in targets
    ]


@router.post("/sync-from-registry", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    db: AsyncSession = Depends(get_db),
    # identity: ServiceIdentity = Depends(get_service_identity)
):
    # correlation_id = identity.correlation_id
    import uuid

    correlation_id = str(uuid.uuid4())  # MOCK temporarily until auth added
    count = await sync_from_registry(db, correlation_id)
    return {
        "status": "accepted",
        "synced_count": count,
        "message": "Synchronized from agent_registry",
    }
