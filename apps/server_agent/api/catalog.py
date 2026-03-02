"""Server Agent API -- catalog (regions, plans, OS images)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.server_agent.models import ServerHost
from apps.server_agent.adapters.factory import get_adapter
from apps.server_agent.client.vault_client import ServerVaultClient
from apps.server_agent.store.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/catalog", tags=["catalog"])


async def _get_adapter_for_host(host_id: str, db: AsyncSession):
    host = await db.get(ServerHost, host_id)
    if not host:
        raise HTTPException(404, "Host not found")
    vault = ServerVaultClient()
    secret = await vault.get_secret(
        alias=host.secret_alias,
        tenant_id=host.tenant_id,
        env=host.env,
        reason="catalog_query",
    )
    return await get_adapter(host.provider, host.config, secret)


@router.get("/regions")
async def list_regions(host_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    adapter = await _get_adapter_for_host(host_id, db)
    return await adapter.list_regions()


@router.get("/plans")
async def list_plans(host_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    adapter = await _get_adapter_for_host(host_id, db)
    return await adapter.list_plans()


@router.get("/os")
async def list_os_images(host_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    adapter = await _get_adapter_for_host(host_id, db)
    return await adapter.list_os_images()
