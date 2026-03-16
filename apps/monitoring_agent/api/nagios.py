"""Nagios API endpoints — hosts, services, overview, problems, CRUD."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.monitoring_agent.client import (
    ServiceDef,
    add_host,
    delete_host,
    edit_host,
    get_host,
    get_host_config,
    get_overview,
    get_problems,
    list_hosts,
    list_services,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/nagios", tags=["nagios"])


# ── Schemas ──


class NagiosHostOut(BaseModel):
    host_name: str
    alias: str = ""
    address: str = ""
    status: int = 0
    status_text: str = "UP"
    plugin_output: str = ""
    perf_data: str = ""
    last_check: int = 0
    last_state_change: int = 0
    current_attempt: int = 0
    max_attempts: int = 0
    has_been_checked: bool = False
    acknowledged: bool = False
    downtime: bool = False


class NagiosServiceOut(BaseModel):
    host_name: str
    service_description: str
    status: int = 0
    status_text: str = "OK"
    plugin_output: str = ""
    perf_data: str = ""
    last_check: int = 0
    last_state_change: int = 0
    current_attempt: int = 0
    max_attempts: int = 0
    has_been_checked: bool = False
    acknowledged: bool = False
    downtime: bool = False
    check_command: str = ""


class NagiosOverviewOut(BaseModel):
    hosts: dict
    services: dict


class NagiosProblemOut(BaseModel):
    type: str  # "host" or "service"
    host_name: str
    service: str | None = None
    status: str
    output: str
    last_check: int = 0
    last_state_change: int = 0
    acknowledged: bool = False


# ── CRUD Schemas ──


class NagiosServiceDefIn(BaseModel):
    description: str = Field(..., description="Service name, e.g. PING")
    check_command: str = Field(
        ..., description="Check command, e.g. check_ping!100.0,20%!500.0,60%"
    )
    check_interval: float | None = Field(
        None, description="Check interval in minutes"
    )


class NagiosHostCreate(BaseModel):
    hostname: str = Field(..., description="FQDN or hostname for the new host")
    alias: str = Field(..., description="Short alias/label for the host")
    address: str = Field(
        ..., description="IP address or DNS name for connectivity checks"
    )
    hostgroup: str = Field("pbx", description="Host group membership")
    services: list[NagiosServiceDefIn] = Field(
        default_factory=list,
        description="Service checks. Empty = default PING only.",
    )


class NagiosHostUpdate(BaseModel):
    alias: str | None = Field(None, description="Updated alias")
    address: str | None = Field(None, description="Updated address")
    hostgroup: str | None = Field(None, description="Updated host group")
    services: list[NagiosServiceDefIn] | None = Field(
        None,
        description="Replacement service list. None = keep existing.",
    )


# ── Converters ──


def _host_to_out(h) -> NagiosHostOut:
    return NagiosHostOut(
        host_name=h.host_name,
        alias=h.alias,
        address=h.address,
        status=h.status,
        status_text=h.status_text,
        plugin_output=h.plugin_output,
        perf_data=h.perf_data,
        last_check=h.last_check,
        last_state_change=h.last_state_change,
        current_attempt=h.current_attempt,
        max_attempts=h.max_attempts,
        has_been_checked=h.has_been_checked,
        acknowledged=h.problem_acknowledged,
        downtime=h.scheduled_downtime_depth > 0,
    )


def _service_to_out(s) -> NagiosServiceOut:
    return NagiosServiceOut(
        host_name=s.host_name,
        service_description=s.service_description,
        status=s.status,
        status_text=s.status_text,
        plugin_output=s.plugin_output,
        perf_data=s.perf_data,
        last_check=s.last_check,
        last_state_change=s.last_state_change,
        current_attempt=s.current_attempt,
        max_attempts=s.max_attempts,
        has_been_checked=s.has_been_checked,
        acknowledged=s.problem_acknowledged,
        downtime=s.scheduled_downtime_depth > 0,
        check_command=s.check_command,
    )


def _service_defs_from_input(
    items: list[NagiosServiceDefIn],
) -> list[ServiceDef]:
    """Convert API input service defs to client ServiceDef objects."""
    return [
        ServiceDef(
            description=s.description,
            check_command=s.check_command,
            check_interval=s.check_interval,
        )
        for s in items
    ]


# ── Read Endpoints ──


@router.get("/overview", response_model=NagiosOverviewOut)
async def nagios_overview(refresh: bool = False):
    """Dashboard overview — host and service counts by status."""
    try:
        if refresh:
            from apps.monitoring_agent.client import refresh_cache

            await refresh_cache()
        return await get_overview()
    except Exception as exc:
        logger.error("nagios_overview_failed", err=str(exc))
        raise HTTPException(502, f"Nagios unavailable: {exc}")


@router.get("/hosts", response_model=list[NagiosHostOut])
async def nagios_hosts(refresh: bool = False):
    """List all Nagios-monitored hosts."""
    try:
        hosts = await list_hosts(force_refresh=refresh)
        return [_host_to_out(h) for h in hosts]
    except Exception as exc:
        logger.error("nagios_hosts_failed", err=str(exc))
        raise HTTPException(502, f"Nagios unavailable: {exc}")


@router.get("/hosts/{hostname}", response_model=NagiosHostOut)
async def nagios_host_detail(hostname: str):
    """Get a single Nagios host by name."""
    try:
        host = await get_host(hostname)
    except Exception as exc:
        logger.error("nagios_host_failed", hostname=hostname, err=str(exc))
        raise HTTPException(502, f"Nagios unavailable: {exc}")
    if not host:
        raise HTTPException(404, f"Host '{hostname}' not found in Nagios")
    return _host_to_out(host)


@router.get("/hosts/{hostname}/services", response_model=list[NagiosServiceOut])
async def nagios_host_services(hostname: str):
    """List all services for a specific host."""
    try:
        services = await list_services(hostname=hostname)
    except Exception as exc:
        logger.error("nagios_services_failed", hostname=hostname, err=str(exc))
        raise HTTPException(502, f"Nagios unavailable: {exc}")
    if not services:
        # Could be host not found or host has no services
        host = await get_host(hostname)
        if not host:
            raise HTTPException(
                404, f"Host '{hostname}' not found in Nagios"
            )
    return [_service_to_out(s) for s in services]


@router.get("/services", response_model=list[NagiosServiceOut])
async def nagios_services_filtered(
    status: str | None = Query(
        None,
        description="Filter by status: OK, WARNING, CRITICAL, UNKNOWN",
    ),
    host: str | None = Query(None, description="Filter by hostname"),
):
    """List services with optional status/host filter."""
    try:
        services = await list_services(hostname=host, status=status)
        return [_service_to_out(s) for s in services]
    except Exception as exc:
        logger.error("nagios_services_failed", err=str(exc))
        raise HTTPException(502, f"Nagios unavailable: {exc}")


@router.get("/problems", response_model=list[NagiosProblemOut])
async def nagios_problems():
    """Get all current problems (DOWN hosts + non-OK services)."""
    try:
        problems = await get_problems()
        return [NagiosProblemOut(**p) for p in problems]
    except Exception as exc:
        logger.error("nagios_problems_failed", err=str(exc))
        raise HTTPException(502, f"Nagios unavailable: {exc}")


# ── CRUD Endpoints ──


@router.post("/hosts", status_code=201)
async def nagios_create_host(body: NagiosHostCreate):
    """Add a new host to Nagios with optional services."""
    try:
        svc_defs = _service_defs_from_input(body.services) if body.services else None
        result = await add_host(
            hostname=body.hostname,
            alias=body.alias,
            address=body.address,
            hostgroup=body.hostgroup,
            services=svc_defs,
        )
        return result
    except ValueError as exc:
        logger.warning("nagios_create_host_failed", err=str(exc))
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("nagios_create_host_error", err=str(exc))
        raise HTTPException(502, f"Nagios error: {exc}")


@router.put("/hosts/{hostname}")
async def nagios_update_host(hostname: str, body: NagiosHostUpdate):
    """Update an existing host's config."""
    try:
        svc_defs = (
            _service_defs_from_input(body.services) if body.services is not None else None
        )
        result = await edit_host(
            hostname=hostname,
            alias=body.alias,
            address=body.address,
            hostgroup=body.hostgroup,
            services=svc_defs,
        )
        return result
    except ValueError as exc:
        logger.warning("nagios_update_host_failed", err=str(exc))
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("nagios_update_host_error", err=str(exc))
        raise HTTPException(502, f"Nagios error: {exc}")


@router.delete("/hosts/{hostname}")
async def nagios_delete_host(hostname: str):
    """Delete a host from Nagios. Creates a backup before removing."""
    try:
        result = await delete_host(hostname)
        return result
    except ValueError as exc:
        logger.warning("nagios_delete_host_failed", err=str(exc))
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("nagios_delete_host_error", err=str(exc))
        raise HTTPException(502, f"Nagios error: {exc}")


@router.get("/hosts/{hostname}/config")
async def nagios_host_config(hostname: str):
    """Get the raw .cfg file content for a host."""
    try:
        config = await get_host_config(hostname)
        return {"hostname": hostname, "config": config}
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        logger.error("nagios_host_config_error", err=str(exc))
        raise HTTPException(502, f"Nagios error: {exc}")

