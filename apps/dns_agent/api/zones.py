"""Zones router — GET /v1/zones, POST /v1/zones."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.dns_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.dns_agent.schemas import ZoneCreate, ZoneOut
from apps.dns_agent.store import postgres as store

router = APIRouter(prefix="/v1/zones", tags=["zones"])


@router.get("", response_model=list[ZoneOut])
async def list_zones(
    tenant_id: str | None = Query(None),
    env: str | None = Query(None),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> list[ZoneOut]:
    """List registered DNS zones. No credential data returned."""
    zones = await store.list_zones(db, tenant_id=tenant_id, env=env)
    return [ZoneOut.model_validate(z) for z in zones]


@router.post("", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
async def create_zone(
    payload: ZoneCreate,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> ZoneOut:
    """Register a new zone and attempt to look up its provider zone ID."""
    from apps.dns_agent.adapters.factory import get_adapter
    from apps.dns_agent.client.vault_client import dns_vault_client_from_env

    existing = await store.get_zone_by_name(db, payload.tenant_id, payload.env, payload.zone_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Zone '{payload.zone_name}' already registered for tenant={payload.tenant_id} env={payload.env}.",
        )

    zone = await store.create_zone(
        db, payload.tenant_id, payload.env, payload.zone_name, payload.provider
    )

    # Attempt to resolve provider zone ID immediately (non-fatal if vault unavailable)
    try:
        vault = dns_vault_client_from_env()
        adapter = await get_adapter(
            payload.provider, payload.tenant_id, payload.env, vault, identity.correlation_id
        )
        provider_zone = await adapter.ensure_zone(payload.zone_name)
        zone = await store.set_provider_zone_id(db, zone, provider_zone.provider_zone_id)
    except Exception as exc:
        # Non-fatal — zone registered; provider ID can be resolved on first sync
        import structlog

        structlog.get_logger().warning(
            "dns_zone_provider_id_lookup_failed",
            zone=payload.zone_name,
            error=str(exc)[:200],
        )

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        tenant_id=payload.tenant_id,
        env=payload.env,
        action="create_zone",
        zone_name=payload.zone_name,
        result="success",
        ip_address=identity.ip_address,
    )
    return ZoneOut.model_validate(zone)
