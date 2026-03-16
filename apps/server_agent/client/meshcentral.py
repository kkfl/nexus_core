"""MeshCentral client — queries devices via SSH + meshctrl.js on the MC server."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import structlog

from apps.server_agent.client.vault_client import ServerVaultClient
from apps.server_agent.config import get_settings

logger = structlog.get_logger(__name__)

# MeshCentral server coordinates (configurable via env)
MC_HOST = "connect.gsmcall.com"
MC_SSH_PORT = 2007
MC_SSH_USER = "root"
MC_WEB_URL = "https://connect.gsmcall.com"
MESHCTRL_PATH = "/opt/meshcentral/node_modules/meshcentral/meshctrl.js"
MC_VAULT_ALIAS = "meshcentral-server-ssh"
MC_LOGIN_VAULT_ALIAS = "meshcentral"
MC_LOGIN_USER = "nexus"

# Cache TTL (seconds) — device list changes rarely, avoid hammering SSH
_CACHE_TTL = 120
_cache: dict[str, tuple[float, list[dict]]] = {}


@dataclass
class MeshDevice:
    """Parsed MeshCentral node."""

    name: str
    node_id: str
    mesh_id: str
    group_name: str
    ip: str | None = None
    os_desc: str | None = None
    connected: bool = False
    powered: bool = False
    last_boot: int | None = None
    agent: dict = field(default_factory=dict)


async def _ssh_exec(cmd: str, ssh_password: str) -> str:
    """Run a command on the MeshCentral server via SSH (pure-Python asyncssh)."""
    import asyncssh  # pure Python — no OS deps needed

    settings = get_settings()
    host = getattr(settings, "meshcentral_ssh_host", MC_HOST)
    port = getattr(settings, "meshcentral_ssh_port", MC_SSH_PORT)
    user = getattr(settings, "meshcentral_ssh_user", MC_SSH_USER)

    try:
        async with asyncssh.connect(
            host,
            port=port,
            username=user,
            password=ssh_password,
            known_hosts=None,  # accept any host key
            connect_timeout=15,
        ) as conn:
            result = await asyncio.wait_for(conn.run(cmd), timeout=30)
            if result.exit_status != 0:
                err = (result.stderr or "").strip()
                logger.error("meshcentral_ssh_failed", cmd=cmd[:80], err=err)
                raise RuntimeError(f"SSH command failed: {err}")
            return result.stdout or ""
    except asyncssh.Error as exc:
        logger.error("meshcentral_ssh_connect_failed", err=str(exc))
        raise RuntimeError(f"SSH connection failed: {exc}")


async def _get_ssh_password() -> str:
    """Fetch the MC server SSH password from vault."""
    vault = ServerVaultClient()
    return await vault.get_secret(
        alias=MC_VAULT_ALIAS,
        tenant_id="default",
        env="prod",
        reason="meshcentral_device_query",
    )


async def _get_mc_password() -> str:
    """Fetch the MeshCentral login password from vault."""
    vault = ServerVaultClient()
    return await vault.get_secret(
        alias=MC_LOGIN_VAULT_ALIAS,
        tenant_id="default",
        env="prod",
        reason="meshcentral_login",
    )


async def _run_meshctrl(action: str, extra_args: str = "") -> str:
    """Run a meshctrl.js command on the MC server."""
    ssh_pw = await _get_ssh_password()
    mc_pw = await _get_mc_password()

    # Build a bash script on the fly to avoid quoting issues
    script = (
        f"cd /opt/meshcentral && "
        f"node {MESHCTRL_PATH} "
        f"--url wss://127.0.0.1 "
        f"--loginuser {MC_LOGIN_USER} "
        f"--loginpass '{mc_pw}' "
        f"{action} {extra_args}"
    )
    return await _ssh_exec(script, ssh_pw)


async def list_devices(force_refresh: bool = False) -> list[MeshDevice]:
    """Return all MeshCentral devices, cached for _CACHE_TTL seconds."""
    import time

    cache_key = "devices"
    now = time.time()

    if not force_refresh and cache_key in _cache:
        ts, cached = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return [_parse_device(d) for d in cached]

    raw = await _run_meshctrl("ListDevices", "--json")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("meshcentral_json_parse_failed", raw=raw[:200])
        raise RuntimeError("Failed to parse MeshCentral device list")

    _cache[cache_key] = (now, data)
    return [_parse_device(d) for d in data]


def _normalize(s: str) -> str:
    """Normalize a name for fuzzy matching: lowercase, strip hyphens/spaces/underscores."""
    import re
    return re.sub(r"[\s\-_]+", "", s.lower())


async def get_device(name: str, ip: str | None = None) -> MeshDevice | None:
    """Look up a MeshCentral device by normalized name or IP address.

    Matching priority:
    1. Exact name match (case-insensitive)
    2. Normalized name match (strip hyphens, spaces, underscores)
    3. IP address match
    """
    devices = await list_devices()
    name_lower = name.lower()
    norm_name = _normalize(name)

    # 1. Exact name match
    for d in devices:
        if d.name.lower() == name_lower:
            return d

    # 2. Normalized name match
    for d in devices:
        if _normalize(d.name) == norm_name:
            return d

    # 3. IP address match
    if ip:
        for d in devices:
            if d.ip and d.ip == ip:
                return d

    return None



def _parse_device(raw: dict) -> MeshDevice:
    """Convert raw meshctrl JSON to MeshDevice dataclass."""
    return MeshDevice(
        name=raw.get("name", ""),
        node_id=raw.get("_id", ""),
        mesh_id=raw.get("meshid", ""),
        group_name=raw.get("groupname", ""),
        ip=raw.get("ip"),
        os_desc=raw.get("osdesc"),
        connected=raw.get("conn", 0) == 1,
        powered=raw.get("pwr", 0) == 1,
        last_boot=raw.get("lastbootuptime"),
        agent=raw.get("agent", {}),
    )
