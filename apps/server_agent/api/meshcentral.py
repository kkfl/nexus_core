"""MeshCentral API endpoints — device listing & info."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from apps.server_agent.client import meshcentral as mc
from apps.server_agent.schemas import MeshDeviceOut

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/meshcentral", tags=["meshcentral"])


@router.get("/devices", response_model=list[MeshDeviceOut])
async def list_meshcentral_devices(refresh: bool = False):
    """List all MeshCentral-managed devices."""
    try:
        devices = await mc.list_devices(force_refresh=refresh)
    except Exception as exc:
        logger.error("meshcentral_list_failed", err=str(exc))
        raise HTTPException(502, f"MeshCentral unavailable: {exc}")
    return [
        MeshDeviceOut(
            name=d.name,
            node_id=d.node_id,
            mesh_id=d.mesh_id,
            group_name=d.group_name,
            ip=d.ip,
            os_desc=d.os_desc,
            connected=d.connected,
            powered=d.powered,
            last_boot=d.last_boot,
        )
        for d in devices
    ]


@router.get("/devices/{name}", response_model=MeshDeviceOut)
async def get_meshcentral_device(name: str, ip: str | None = None):
    """Look up a single MeshCentral device by hostname (with fuzzy matching + IP fallback)."""
    try:
        device = await mc.get_device(name, ip=ip)
    except Exception as exc:
        logger.error("meshcentral_get_failed", name=name, err=str(exc))
        raise HTTPException(502, f"MeshCentral unavailable: {exc}")
    if not device:
        raise HTTPException(404, f"Device '{name}' not found in MeshCentral")
    return MeshDeviceOut(
        name=device.name,
        node_id=device.node_id,
        mesh_id=device.mesh_id,
        group_name=device.group_name,
        ip=device.ip,
        os_desc=device.os_desc,
        connected=device.connected,
        powered=device.powered,
        last_boot=device.last_boot,
    )
