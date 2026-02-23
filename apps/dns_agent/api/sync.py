"""Sync router — POST /v1/sync — drift detection and optional reconciliation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.dns_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.dns_agent.adapters.factory import get_adapter
from apps.dns_agent.client.vault_client import dns_vault_client_from_env
from apps.dns_agent.jobs.runner import dispatch_job
from apps.dns_agent.schemas import DriftRecord, JobCreateResponse, SyncRequest, SyncResult
from apps.dns_agent.store import postgres as store

router = APIRouter(prefix="/v1/sync", tags=["sync"])


@router.post("", response_model=SyncResult)
async def sync_zone(
    payload: SyncRequest,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(store.get_db),
) -> SyncResult:
    """
    Pull current provider state, compare with desired Nexus state, and return a drift report.
    If reconcile=true, create a change job to apply missing/changed records.

    Provider API tokens are fetched from secrets_agent — never returned in the response.
    """
    zone = await store.get_zone_by_name(db, payload.tenant_id, payload.env, payload.zone)
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Zone '{payload.zone}' not found for tenant={payload.tenant_id} env={payload.env}.")
    if not zone.provider_zone_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Zone has no provider_zone_id — use POST /v1/zones to re-register and resolve provider zone ID.")

    vault = dns_vault_client_from_env()
    adapter = await get_adapter(zone.provider, payload.tenant_id, payload.env, vault,
                                identity.correlation_id)

    # Fetch live provider records
    provider_records = await adapter.list_records(zone.provider_zone_id)
    provider_map = {(r.record_type, r.name): r for r in provider_records}

    # Fetch desired Nexus records
    nexus_records = await store.list_records(db, zone.id)
    nexus_map = {(r.record_type, r.name): r for r in nexus_records}

    drift: list[DriftRecord] = []

    # Records in Nexus but wrong/missing in provider
    for (rtype, name), desired in nexus_map.items():
        actual = provider_map.get((rtype, name))
        actual_val = actual.value if actual else None
        if actual_val != desired.value:
            drift.append(DriftRecord(
                record_type=rtype,
                name=name,
                expected=desired.value,
                actual=actual_val,
            ))

    job_id = None
    if payload.reconcile and drift:
        # Create a reconcile upsert job for drifted records
        records_to_fix = []
        for d in drift:
            desired = nexus_map.get((d.record_type, d.name))
            if desired:
                records_to_fix.append({
                    "record_type": d.record_type,
                    "name": d.name,
                    "value": desired.value,
                    "ttl": desired.ttl,
                    "priority": desired.priority,
                })
        job = await store.create_job(
            db, payload.tenant_id, payload.env, payload.zone,
            operation="upsert",
            payload={"records": records_to_fix},
            service_id=identity.service_id,
            correlation_id=identity.correlation_id,
        )
        from apps.dns_agent.store.postgres import _session_factory
        dispatch_job(job, _session_factory)
        job_id = job.id

    await store.log_audit(
        db, correlation_id=identity.correlation_id, service_id=identity.service_id,
        tenant_id=payload.tenant_id, env=payload.env, action="sync",
        zone_name=payload.zone, result="success",
        reason=f"drift_count={len(drift)}, reconcile={payload.reconcile}",
        ip_address=identity.ip_address,
    )

    return SyncResult(
        zone=payload.zone,
        tenant_id=payload.tenant_id,
        env=payload.env,
        provider=zone.provider,
        drift_count=len(drift),
        drift=drift,
        reconciled=payload.reconcile and len(drift) > 0,
        job_id=job_id,
    )
