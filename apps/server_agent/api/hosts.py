"""Server Agent API -- hosts (provider connection registry)."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.server_agent.adapters.proxmox import ProxmoxAdapter
from apps.server_agent.client.vault_client import ServerVaultClient
from apps.server_agent.config import get_settings
from apps.server_agent.models import ServerHost
from apps.server_agent.schemas import HostCreate, HostOut, HostResourcesOut
from apps.server_agent.store.postgres import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/hosts", tags=["hosts"])


@router.get("", response_model=list[HostOut])
async def list_hosts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServerHost).order_by(ServerHost.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=HostOut, status_code=201)
async def create_host(body: HostCreate, db: AsyncSession = Depends(get_db)):
    host = ServerHost(
        id=str(uuid.uuid4()),
        tenant_id=body.tenant_id,
        env=body.env,
        provider=body.provider,
        label=body.label,
        config=body.config,
        secret_alias=body.secret_alias,
    )
    db.add(host)
    await db.commit()
    await db.refresh(host)
    logger.info("host_created", host_id=host.id, provider=body.provider, label=body.label)
    return host


@router.get("/{host_id}/resources", response_model=HostResourcesOut)
async def get_host_resources(host_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch live node-level resource usage (Proxmox only)."""
    host = await db.get(ServerHost, host_id)
    if not host:
        raise HTTPException(404, "Host not found")

    if host.provider != "proxmox":
        raise HTTPException(
            400,
            f"Resource monitoring not available for provider '{host.provider}' "
            "(only Proxmox hosts have finite node resources)",
        )

    try:
        settings = get_settings()
        vault = ServerVaultClient()
        secret = await vault.get_secret(
            alias=host.secret_alias,
            tenant_id=host.tenant_id,
            env=host.env,
            reason="host_resources_check",
        )

        adapter = ProxmoxAdapter(
            base_url=host.config.get("base_url", ""),
            api_token=secret,
            node=host.config.get("node", "pve"),
            verify_ssl=settings.proxmox_verify_ssl,
        )

        status = await adapter.get_node_status()
        return HostResourcesOut(provider="proxmox", **status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("host_resources_failed", host_id=host_id, error=str(e))
        raise HTTPException(502, f"Failed to fetch host resources: {e}")


@router.delete("/{host_id}", status_code=204)
async def delete_host(host_id: str, db: AsyncSession = Depends(get_db)):
    host = await db.get(ServerHost, host_id)
    if not host:
        raise HTTPException(404, "Host not found")
    await db.delete(host)
    await db.commit()
    logger.info("host_deleted", host_id=host_id)
