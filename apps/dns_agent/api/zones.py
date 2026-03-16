"""Zones router — GET /v1/zones, POST /v1/zones."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.dns_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.dns_agent.schemas import RecordOut, ZoneCreate, ZoneOut
from apps.dns_agent.store import postgres as store
from packages.shared.alerts import send_alert
from packages.shared.events.api import emit_event

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/zones", tags=["zones"])


@router.get("", response_model=list[ZoneOut])
async def list_zones(
    tenant_id: str | None = Query(None),
    env: str | None = Query(None),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> list[ZoneOut]:
    """List registered DNS zones with record counts. No credential data returned."""
    zones = await store.list_zones(db, tenant_id=tenant_id, env=env)
    record_counts = await store.count_records_by_zone(db, [z.id for z in zones])
    result = []
    for z in zones:
        out = ZoneOut.model_validate(z)
        out.record_count = record_counts.get(z.id, 0)
        result.append(out)
    return result


@router.get("/{zone_id}/records", response_model=list[RecordOut])
async def list_zone_records(
    zone_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> list[RecordOut]:
    """List DNS records for a zone by zone ID."""
    zone = await store.get_zone(db, zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found.",
        )
    records = await store.list_records(db, zone.id)
    return [RecordOut.model_validate(r) for r in records]


@router.delete("/{zone_id}", status_code=status.HTTP_200_OK)
async def unregister_zone(
    zone_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> dict:
    """
    Remove a zone and all its records from the LOCAL Nexus database only.

    ⚠ This does NOT delete anything from the DNS provider (DNSMadeEasy, Cloudflare).
    The zone and its records remain untouched at the provider.
    This only removes the Nexus monitoring/tracking of the zone.
    """
    zone = await store.get_zone(db, zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zone '{zone_id}' not found.",
        )

    zone_name = zone.zone_name
    tenant_id = zone.tenant_id
    env = zone.env

    await store.delete_zone(db, zone)

    await store.log_audit(
        db,
        correlation_id=identity.correlation_id,
        service_id=identity.service_id,
        tenant_id=tenant_id,
        env=env,
        action="unregister_zone",
        zone_name=zone_name,
        result="success",
        reason="Removed from Nexus only — provider records untouched",
        ip_address=identity.ip_address,
    )

    # Emit event (fire-and-forget — Redis failure won't break the operation)
    try:
        await emit_event(
            event_type="dns.zone.unregistered",
            payload={"zone_name": zone_name, "tenant_id": tenant_id, "env": env},
            produced_by="dns-agent",
            tenant_id=tenant_id,
            correlation_id=identity.correlation_id,
            tags=["dns", "zone", "unregister"],
            db=db,
        )
    except Exception:
        logger.warning("event_emit_failed", event_type="dns.zone.unregistered")

    send_alert("dns_zone_delete", identity.service_id, f"Zone: {zone_name}")

    return {
        "status": "removed",
        "zone_name": zone_name,
        "detail": "Zone and records removed from Nexus only. DNS provider records are untouched.",
    }


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

    try:
        await emit_event(
            event_type="dns.zone.created",
            payload={
                "zone_name": payload.zone_name,
                "provider": payload.provider,
                "tenant_id": payload.tenant_id,
                "env": payload.env,
            },
            produced_by="dns-agent",
            tenant_id=payload.tenant_id,
            correlation_id=identity.correlation_id,
            tags=["dns", "zone", "create"],
            db=db,
        )
    except Exception:
        logger.warning("event_emit_failed", event_type="dns.zone.created")

    send_alert(
        "dns_zone_create",
        identity.service_id,
        f"Zone: {payload.zone_name} (provider: {payload.provider})",
    )

    return ZoneOut.model_validate(zone)


@router.get("/discover", response_model=list[dict])
async def discover_provider_zones(
    provider: str = Query(..., description="cloudflare | dnsmadeeasy"),
    tenant_id: str = Query("gsm"),
    env: str = Query("prod"),
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> list[dict]:
    """
    List zones directly from a DNS provider (live API call).
    Uses credentials from secrets_agent — no credentials returned in response.
    Useful for discovering existing zones that can be imported into Nexus.
    """
    from apps.dns_agent.adapters.factory import get_adapter
    from apps.dns_agent.client.vault_client import dns_vault_client_from_env

    vault = dns_vault_client_from_env()
    adapter = await get_adapter(provider, tenant_id, env, vault, identity.correlation_id)
    zones = await adapter.list_zones()

    # Cross-reference with already-registered zones
    registered = await store.list_zones(db, tenant_id=tenant_id, env=env)
    registered_names = {z.zone_name for z in registered}

    return [
        {
            "provider_zone_id": z.provider_zone_id,
            "zone_name": z.zone_name,
            "status": z.status,
            "registered": z.zone_name in registered_names,
        }
        for z in zones
    ]


from typing import Any

from pydantic import BaseModel


class ZoneImportRequest(BaseModel):
    provider: str
    tenant_id: str
    env: str
    zone_names: list[str]


@router.post("/import", response_model=list[ZoneOut])
async def import_provider_zones(
    payload: ZoneImportRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> list[ZoneOut]:
    """
    Bulk-import zones from a DNS provider into Nexus.
    Discovers provider zone IDs and registers them in the dns_agent database.
    Skips zones that are already registered.
    """
    from apps.dns_agent.adapters.factory import get_adapter
    from apps.dns_agent.client.vault_client import dns_vault_client_from_env

    vault = dns_vault_client_from_env()
    adapter = await get_adapter(
        payload.provider, payload.tenant_id, payload.env, vault, identity.correlation_id
    )
    provider_zones = await adapter.list_zones()
    provider_map = {z.zone_name: z for z in provider_zones}

    imported: list[Any] = []
    for name in payload.zone_names:
        name = name.lower().strip(".")
        existing = await store.get_zone_by_name(db, payload.tenant_id, payload.env, name)
        if existing:
            imported.append(existing)
            continue

        try:
            zone = await store.create_zone(
                db, payload.tenant_id, payload.env, name, payload.provider
            )
        except IntegrityError:
            await db.rollback()
            # Zone was created between the check and the insert — fetch it
            existing = await store.get_zone_by_name(db, payload.tenant_id, payload.env, name)
            if existing:
                imported.append(existing)
                continue
            raise

        pz = provider_map.get(name)
        if pz:
            zone = await store.set_provider_zone_id(db, zone, pz.provider_zone_id)

            # Pull DNS records from the provider so the zone isn't empty
            try:
                provider_records = await adapter.list_records(pz.provider_zone_id)
                for rec in provider_records:
                    await store.upsert_record(
                        db,
                        zone=zone,
                        record_type=rec.record_type,
                        name=rec.name,
                        value=rec.value,
                        ttl=rec.ttl,
                        priority=rec.priority,
                        tags=None,
                        provider_record_id=rec.provider_record_id,
                    )
            except Exception as exc:
                # Non-fatal — zone is imported; records can be pulled via sync later
                import structlog

                structlog.get_logger().warning(
                    "dns_import_records_failed",
                    zone=name,
                    error=str(exc)[:200],
                )

        await store.log_audit(
            db,
            correlation_id=identity.correlation_id,
            service_id=identity.service_id,
            tenant_id=payload.tenant_id,
            env=payload.env,
            action="import_zone",
            zone_name=name,
            result="success",
            ip_address=identity.ip_address,
        )

        try:
            await emit_event(
                event_type="dns.zone.imported",
                payload={
                    "zone_name": name,
                    "provider": payload.provider,
                    "tenant_id": payload.tenant_id,
                    "env": payload.env,
                },
                produced_by="dns-agent",
                tenant_id=payload.tenant_id,
                correlation_id=identity.correlation_id,
                tags=["dns", "zone", "import"],
                db=db,
            )
        except Exception:
            logger.warning("event_emit_failed", event_type="dns.zone.imported")

        imported.append(zone)

    # Refresh each zone to eagerly load all scalar attrs (created_at,
    # updated_at are server_default) so Pydantic doesn't trigger a lazy
    # relationship load (records) in the sync validation context.
    for z in imported:
        await db.refresh(
            z,
            attribute_names=[
                "id",
                "tenant_id",
                "env",
                "zone_name",
                "provider",
                "provider_zone_id",
                "is_active",
                "created_at",
                "updated_at",
            ],
        )
    return [ZoneOut.model_validate(z) for z in imported]
