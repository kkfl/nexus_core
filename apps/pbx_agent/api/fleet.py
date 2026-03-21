"""
Fleet API — GET /v1/fleet/status, GET /v1/fleet/summary, POST /v1/fleet/refresh

Aggregated PBX fleet view combining AMI diagnostics + SSH system metrics.
Uses background polling with in-memory cache.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.pbx_agent.adapters import ami
from apps.pbx_agent.adapters.ssh_system import check_ssh_connectivity, collect_node_snapshot
from apps.pbx_agent.auth.identity import ServiceIdentity, get_service_identity
from apps.pbx_agent.client.secrets import SecretsError, fetch_secret
from apps.pbx_agent.models import PbxTarget
from apps.pbx_agent.schemas import PbxFleetNodeOut, PbxFleetStatusOut, PbxFleetSummaryOut
from apps.pbx_agent.store.database import async_session, get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/fleet", tags=["fleet"])

# ── In-memory cache ──────────────────────────────────────────────────────────
_fleet_cache: PbxFleetStatusOut | None = None
_fleet_cache_ts: float = 0
_fleet_refreshing = False
_fleet_lock = asyncio.Lock()

CACHE_TTL = 60  # seconds


async def _fetch_ssh_creds(target: PbxTarget) -> tuple[str | None, str | None]:
    """Fetch SSH key PEM and/or password from vault."""
    key_pem = None
    password = None

    if target.ssh_key_alias:
        try:
            key_pem = await fetch_secret(
                alias=target.ssh_key_alias,
                tenant_id=target.tenant_id,
                env=target.env,
                reason="fleet_status",
            )
        except SecretsError as e:
            logger.warning("ssh_key_fetch_failed", alias=target.ssh_key_alias, error=str(e)[:200])

    if target.ssh_password_alias:
        try:
            password = await fetch_secret(
                alias=target.ssh_password_alias,
                tenant_id=target.tenant_id,
                env=target.env,
                reason="fleet_status",
            )
        except SecretsError as e:
            logger.warning("ssh_password_fetch_failed", alias=target.ssh_password_alias, error=str(e)[:200])

    return key_pem, password


async def _poll_single_target(target: PbxTarget) -> PbxFleetNodeOut:
    """Poll a single PBX target via SSH and return fleet node status."""
    node = PbxFleetNodeOut(
        target_id=target.id,
        name=target.name,
        host=target.host,
        status=target.status,
    )

    if target.status != "active":
        return node

    # Step 1: Check network reachability (SSH port open?)
    # This determines online/offline — separate from SSH auth
    node.online = await check_ssh_connectivity(target.host, target.ssh_port)

    if not node.online:
        node.poll_error = f"SSH port {target.ssh_port} unreachable on {target.host}"
        return node

    # Step 2: Fetch SSH credentials
    key_pem, password = await _fetch_ssh_creds(target)

    if not key_pem and not password:
        node.poll_error = "No SSH credentials configured"
        return node

    # Step 3: Collect snapshot via SSH (auth + commands)
    snap = await collect_node_snapshot(
        host=target.host,
        port=target.ssh_port,
        username=target.ssh_username,
        private_key_pem=key_pem,
        password=password,
    )

    # Keep online status from network check — SSH auth failure ≠ offline
    node.ssh_ok = snap.ssh_ok
    if not snap.ssh_ok:
        node.poll_error = snap.error

    if snap.ssh_ok:
        # System metrics
        node.cpu_pct = snap.system.cpu_pct
        node.ram_used_mb = snap.system.ram_used_mb
        node.ram_total_mb = snap.system.ram_total_mb
        node.ram_pct = snap.system.ram_pct
        node.disk_used_gb = snap.system.disk_used_gb
        node.disk_total_gb = snap.system.disk_total_gb
        node.disk_pct = snap.system.disk_pct

        # Asterisk status
        node.asterisk_up = snap.asterisk.asterisk_up
        node.asterisk_version = snap.asterisk.version
        node.active_calls = snap.asterisk.active_calls
        node.sip_registrations = snap.asterisk.sip_registrations
        node.calls_24h = snap.asterisk.calls_24h
        node.uptime_seconds = snap.asterisk.uptime_seconds
        node.uptime_human = snap.asterisk.uptime_human

        # AMI status: test actual AMI login with credentials
        if snap.asterisk.asterisk_up:
            try:
                ami_secret = await fetch_secret(
                    alias=target.ami_secret_alias,
                    tenant_id=target.tenant_id,
                    env=target.env,
                    reason="fleet_status_ami",
                )
                node.ami_ok = await ami.check_ami_login(
                    host=target.host, port=target.ami_port,
                    username=target.ami_username, secret=ami_secret,
                )
            except Exception:
                node.ami_ok = False

    node.last_polled_at = datetime.now(UTC)
    return node


def _build_summary(nodes: list[PbxFleetNodeOut]) -> PbxFleetSummaryOut:
    """Compute aggregate fleet stats from node list."""
    active_nodes = [n for n in nodes if n.status == "active"]
    online = [n for n in active_nodes if n.online]
    offline = [n for n in active_nodes if not n.online]

    cpu_vals = [n.cpu_pct for n in online if n.cpu_pct is not None]
    ram_vals = [n.ram_pct for n in online if n.ram_pct is not None]
    disk_vals = [n.disk_pct for n in online if n.disk_pct is not None]

    return PbxFleetSummaryOut(
        total_targets=len(active_nodes),
        online=len(online),
        offline=len(offline),
        asterisk_up=sum(1 for n in online if n.asterisk_up),
        asterisk_down=sum(1 for n in online if not n.asterisk_up),
        total_active_calls=sum(n.active_calls for n in online),
        total_calls_24h=sum(n.calls_24h for n in online),
        total_registrations=sum(n.sip_registrations for n in online),
        avg_cpu_pct=round(sum(cpu_vals) / len(cpu_vals), 1) if cpu_vals else None,
        avg_ram_pct=round(sum(ram_vals) / len(ram_vals), 1) if ram_vals else None,
        avg_disk_pct=round(sum(disk_vals) / len(disk_vals), 1) if disk_vals else None,
        last_polled_at=datetime.now(UTC),
    )


async def _refresh_fleet() -> PbxFleetStatusOut:
    """Poll all active targets and build fleet status."""
    global _fleet_cache, _fleet_cache_ts, _fleet_refreshing

    _fleet_refreshing = True
    try:
        async with async_session() as db:
            result = await db.execute(
                select(PbxTarget).where(PbxTarget.status == "active")
            )
            targets = result.scalars().all()

        logger.info("fleet_poll_start", target_count=len(targets))

        # Poll all targets concurrently (with a semaphore to limit parallelism)
        sem = asyncio.Semaphore(5)

        async def _limited_poll(t):
            async with sem:
                return await _poll_single_target(t)

        nodes = await asyncio.gather(*[_limited_poll(t) for t in targets])
        nodes = list(nodes)

        summary = _build_summary(nodes)

        status = PbxFleetStatusOut(
            nodes=nodes,
            summary=summary,
            refreshing=False,
            collected_at=datetime.now(UTC),
        )

        _fleet_cache = status
        _fleet_cache_ts = time.time()

        logger.info(
            "fleet_poll_complete",
            online=summary.online,
            offline=summary.offline,
            active_calls=summary.total_active_calls,
        )
        return status
    except Exception as e:
        logger.error("fleet_poll_error", error=str(e)[:200])
        return PbxFleetStatusOut()
    finally:
        _fleet_refreshing = False


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/status", response_model=PbxFleetStatusOut)
async def fleet_status(
    identity: ServiceIdentity = Depends(get_service_identity),
):
    """Return cached fleet status. Triggers background refresh if stale."""
    global _fleet_cache, _fleet_cache_ts

    now = time.time()
    is_stale = (now - _fleet_cache_ts) > CACHE_TTL

    if _fleet_cache is None or is_stale:
        if not _fleet_refreshing:
            asyncio.create_task(_refresh_fleet())

    if _fleet_cache:
        return _fleet_cache

    # First call — wait for refresh
    return await _refresh_fleet()


@router.get("/status/{target_id}", response_model=PbxFleetNodeOut)
async def fleet_node_status(
    target_id: str,
    identity: ServiceIdentity = Depends(get_service_identity),
    db: AsyncSession = Depends(get_db),
):
    """Get fresh status for a single PBX node (not cached)."""
    result = await db.execute(select(PbxTarget).where(PbxTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail=f"Target '{target_id}' not found")
    return await _poll_single_target(target)


@router.get("/summary", response_model=PbxFleetSummaryOut)
async def fleet_summary(
    identity: ServiceIdentity = Depends(get_service_identity),
):
    """Return aggregate fleet summary (from cache)."""
    if _fleet_cache:
        return _fleet_cache.summary
    status = await _refresh_fleet()
    return status.summary


@router.post("/refresh")
async def fleet_refresh(
    identity: ServiceIdentity = Depends(get_service_identity),
):
    """Force re-poll all targets immediately."""
    if _fleet_refreshing:
        return {"ok": True, "message": "Refresh already in progress"}
    status = await _refresh_fleet()
    return {
        "ok": True,
        "count": len(status.nodes),
        "online": status.summary.online,
        "offline": status.summary.offline,
    }


# ── Background poller (called from lifespan) ────────────────────────────────


async def fleet_background_poller(interval: int = 60):
    """Background task that polls fleet status on a timer."""
    logger.info("fleet_background_poller_started", interval=interval)
    while True:
        try:
            await asyncio.sleep(interval)
            if not _fleet_refreshing:
                await _refresh_fleet()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("fleet_poll_bg_error", error=str(e)[:200])
            await asyncio.sleep(10)
