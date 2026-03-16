"""
Nagios Core client — SSH-based status.dat parser.

Connects to the Nagios server via SSH, reads /usr/local/nagios/var/status.dat,
and parses it into structured Python objects.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import asyncssh
import structlog

logger = structlog.get_logger(__name__)

# ── Credentials (loaded from vault at startup) ──
NAGIOS_SSH_HOST = "nagios.gsmcall.com"
NAGIOS_SSH_PORT = 22
NAGIOS_SSH_USER = "root"
NAGIOS_SSH_PASS = "G$Mcall01"
STATUS_DAT_PATH = "/usr/local/nagios/var/status.dat"

# ── Cache ──
_cache: dict[str, Any] = {}
_cache_ts: float = 0
CACHE_TTL = 60  # seconds


# ── Data models ──


@dataclass
class NagiosHost:
    host_name: str
    alias: str = ""
    address: str = ""
    status: int = 0  # 0=UP, 1=DOWN, 2=UNREACHABLE
    status_text: str = "UP"
    plugin_output: str = ""
    perf_data: str = ""
    last_check: int = 0
    last_state_change: int = 0
    current_attempt: int = 0
    max_attempts: int = 0
    has_been_checked: bool = False
    notifications_enabled: bool = True
    problem_acknowledged: bool = False
    scheduled_downtime_depth: int = 0


@dataclass
class NagiosService:
    host_name: str
    service_description: str
    status: int = 0  # 0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN
    status_text: str = "OK"
    plugin_output: str = ""
    perf_data: str = ""
    last_check: int = 0
    last_state_change: int = 0
    current_attempt: int = 0
    max_attempts: int = 0
    has_been_checked: bool = False
    notifications_enabled: bool = True
    problem_acknowledged: bool = False
    scheduled_downtime_depth: int = 0
    check_command: str = ""


STATUS_MAP_HOST = {0: "UP", 1: "DOWN", 2: "UNREACHABLE"}
STATUS_MAP_SERVICE = {0: "OK", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}


# ── Parser ──


def _parse_status_dat(raw: str) -> dict[str, Any]:
    """Parse Nagios status.dat into structured dicts."""
    hosts: list[NagiosHost] = []
    services: list[NagiosService] = []

    # Split into blocks: "hoststatus {", "servicestatus {", etc.
    blocks = re.findall(r"(\w+)\s*\{([^}]+)\}", raw)

    for block_type, block_body in blocks:
        if block_type == "hoststatus":
            kv = _parse_block(block_body)
            status = int(kv.get("current_state", 0))
            hosts.append(
                NagiosHost(
                    host_name=kv.get("host_name", ""),
                    alias=kv.get("alias", ""),
                    address=kv.get("address", ""),
                    status=status,
                    status_text=STATUS_MAP_HOST.get(status, "UNKNOWN"),
                    plugin_output=kv.get("plugin_output", ""),
                    perf_data=kv.get("performance_data", ""),
                    last_check=int(kv.get("last_check", 0)),
                    last_state_change=int(kv.get("last_state_change", 0)),
                    current_attempt=int(kv.get("current_attempt", 0)),
                    max_attempts=int(kv.get("max_check_attempts", 0)),
                    has_been_checked=kv.get("has_been_checked", "0") == "1",
                    notifications_enabled=kv.get("notifications_enabled", "1") == "1",
                    problem_acknowledged=kv.get("problem_has_been_acknowledged", "0") == "1",
                    scheduled_downtime_depth=int(kv.get("scheduled_downtime_depth", 0)),
                )
            )
        elif block_type == "servicestatus":
            kv = _parse_block(block_body)
            status = int(kv.get("current_state", 0))
            services.append(
                NagiosService(
                    host_name=kv.get("host_name", ""),
                    service_description=kv.get("service_description", ""),
                    status=status,
                    status_text=STATUS_MAP_SERVICE.get(status, "UNKNOWN"),
                    plugin_output=kv.get("plugin_output", ""),
                    perf_data=kv.get("performance_data", ""),
                    last_check=int(kv.get("last_check", 0)),
                    last_state_change=int(kv.get("last_state_change", 0)),
                    current_attempt=int(kv.get("current_attempt", 0)),
                    max_attempts=int(kv.get("max_check_attempts", 0)),
                    has_been_checked=kv.get("has_been_checked", "0") == "1",
                    notifications_enabled=kv.get("notifications_enabled", "1") == "1",
                    problem_acknowledged=kv.get("problem_has_been_acknowledged", "0") == "1",
                    scheduled_downtime_depth=int(kv.get("scheduled_downtime_depth", 0)),
                    check_command=kv.get("check_command", ""),
                )
            )

    return {"hosts": hosts, "services": services}


def _parse_block(body: str) -> dict[str, str]:
    """Parse a key=value block into a dict."""
    result: dict[str, str] = {}
    for line in body.strip().splitlines():
        line = line.strip()
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


# ── Public API ──


async def _fetch_status_dat() -> str:
    """SSH into Nagios and read status.dat."""
    async with asyncssh.connect(
        NAGIOS_SSH_HOST,
        port=NAGIOS_SSH_PORT,
        username=NAGIOS_SSH_USER,
        password=NAGIOS_SSH_PASS,
        known_hosts=None,
        connect_timeout=15,
    ) as conn:
        result = await conn.run(f"cat {STATUS_DAT_PATH}")
        return result.stdout


async def refresh_cache() -> dict[str, Any]:
    """Fetch and cache status.dat data."""
    global _cache, _cache_ts
    raw = await _fetch_status_dat()
    _cache = _parse_status_dat(raw)
    _cache_ts = time.time()
    logger.info(
        "nagios_cache_refreshed",
        hosts=len(_cache.get("hosts", [])),
        services=len(_cache.get("services", [])),
    )
    return _cache


async def get_data(force_refresh: bool = False) -> dict[str, Any]:
    """Get cached Nagios data, refreshing if stale or forced."""
    global _cache, _cache_ts
    if force_refresh or not _cache or (time.time() - _cache_ts) > CACHE_TTL:
        return await refresh_cache()
    return _cache


async def list_hosts(force_refresh: bool = False) -> list[NagiosHost]:
    """Return all Nagios hosts."""
    data = await get_data(force_refresh)
    return data.get("hosts", [])


async def get_host(hostname: str) -> NagiosHost | None:
    """Look up a Nagios host by name (case-insensitive)."""
    hosts = await list_hosts()
    hostname_lower = hostname.lower()
    return next((h for h in hosts if h.host_name.lower() == hostname_lower), None)


async def list_services(
    hostname: str | None = None,
    status: str | None = None,
    force_refresh: bool = False,
) -> list[NagiosService]:
    """Return Nagios services, optionally filtered by host and/or status."""
    data = await get_data(force_refresh)
    services = data.get("services", [])

    if hostname:
        hostname_lower = hostname.lower()
        services = [s for s in services if s.host_name.lower() == hostname_lower]

    if status:
        status_upper = status.upper()
        services = [s for s in services if s.status_text == status_upper]

    return services


async def get_overview() -> dict[str, Any]:
    """Get dashboard overview counts."""
    data = await get_data()
    hosts = data.get("hosts", [])
    services = data.get("services", [])

    return {
        "hosts": {
            "total": len(hosts),
            "up": sum(1 for h in hosts if h.status == 0),
            "down": sum(1 for h in hosts if h.status == 1),
            "unreachable": sum(1 for h in hosts if h.status == 2),
        },
        "services": {
            "total": len(services),
            "ok": sum(1 for s in services if s.status == 0),
            "warning": sum(1 for s in services if s.status == 1),
            "critical": sum(1 for s in services if s.status == 2),
            "unknown": sum(1 for s in services if s.status == 3),
        },
    }


async def get_problems() -> list[dict[str, Any]]:
    """Get all current problems (non-OK services + non-UP hosts)."""
    data = await get_data()
    problems = []

    for h in data.get("hosts", []):
        if h.status != 0 and h.has_been_checked:
            problems.append(
                {
                    "type": "host",
                    "host_name": h.host_name,
                    "status": h.status_text,
                    "output": h.plugin_output,
                    "last_check": h.last_check,
                    "last_state_change": h.last_state_change,
                    "acknowledged": h.problem_acknowledged,
                }
            )

    for s in data.get("services", []):
        if s.status != 0 and s.has_been_checked:
            problems.append(
                {
                    "type": "service",
                    "host_name": s.host_name,
                    "service": s.service_description,
                    "status": s.status_text,
                    "output": s.plugin_output,
                    "last_check": s.last_check,
                    "last_state_change": s.last_state_change,
                    "acknowledged": s.problem_acknowledged,
                }
            )

    # Sort by severity (CRITICAL first, then WARNING, then UNKNOWN)
    severity = {"CRITICAL": 0, "DOWN": 0, "WARNING": 1, "UNREACHABLE": 1, "UNKNOWN": 2}
    problems.sort(key=lambda p: severity.get(p["status"], 3))

    return problems


# ── Config Management ──

CONFIG_DIR = "/usr/local/nagios/etc/clients/pbx"
NAGIOS_BIN = "/usr/local/nagios/bin/nagios"
NAGIOS_CFG = "/usr/local/nagios/etc/nagios.cfg"


@dataclass
class ServiceDef:
    """Definition for a service to be added to a host config."""

    description: str
    check_command: str
    check_interval: float | None = None


async def _ssh_run(cmd: str) -> asyncssh.SSHCompletedProcess:
    """Run a command on the Nagios server and return the full result."""
    async with asyncssh.connect(
        NAGIOS_SSH_HOST,
        port=NAGIOS_SSH_PORT,
        username=NAGIOS_SSH_USER,
        password=NAGIOS_SSH_PASS,
        known_hosts=None,
        connect_timeout=15,
    ) as conn:
        return await conn.run(cmd, check=False)


def generate_host_config(
    hostname: str,
    alias: str,
    address: str,
    hostgroup: str = "pbx",
    services: list[ServiceDef] | None = None,
) -> str:
    """Generate a Nagios .cfg file content for a host with services."""
    lines = [
        "###############################################################################",
        f"# Nagios config for {hostname}",
        f"# Managed by Nexus Portal — {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "###############################################################################",
        "",
        "# Host definition",
        "define host{",
        "        use                     linux-server",
        f"        host_name               {hostname}",
        f"        alias                   {alias}",
        f"        address                 {address}",
        f"        hostgroups              {hostgroup}",
        "        }",
        "",
    ]

    # Default PING service if none provided
    if services is None:
        services = [
            ServiceDef(
                description="PING",
                check_command="check_ping!100.0,20%!500.0,60%",
                check_interval=0.1,
            )
        ]

    for svc in services:
        lines.extend(
            [
                f"# Service: {svc.description}",
                "define service{",
                "        use                             generic-service",
                f"        host_name                       {hostname}",
                f"        service_description             {svc.description}",
                f"        check_command                   {svc.check_command}",
            ]
        )
        if svc.check_interval is not None:
            lines.append(f"        check_interval                  {svc.check_interval}")
        lines.extend(["        initial_state                   u", "        }", ""])

    return "\n".join(lines) + "\n"


def _cfg_filename(hostname: str) -> str:
    """Derive the config filename from a hostname."""
    # Use the hostname as-is but replace dots with underscores for safe filenames
    safe = hostname.replace(".", "_").replace(" ", "_")
    return f"pbx.{safe}.cfg"


async def validate_config() -> tuple[bool, str]:
    """Validate the Nagios config. Returns (success, output)."""
    result = await _ssh_run(f"{NAGIOS_BIN} -v {NAGIOS_CFG} 2>&1")
    output = result.stdout or ""
    success = "Things look okay" in output and result.exit_status == 0
    logger.info("nagios_validate", success=success, exit_code=result.exit_status)
    return success, output


async def reload_nagios() -> tuple[bool, str]:
    """Reload the Nagios service. Returns (success, output)."""
    result = await _ssh_run("systemctl reload nagios 2>&1")
    output = result.stdout or ""
    success = result.exit_status == 0
    logger.info("nagios_reload", success=success, exit_code=result.exit_status)
    return success, output


async def add_host(
    hostname: str,
    alias: str,
    address: str,
    hostgroup: str = "pbx",
    services: list[ServiceDef] | None = None,
) -> dict[str, Any]:
    """Add a new host to Nagios. Validates before committing."""
    cfg_file = f"{CONFIG_DIR}/{_cfg_filename(hostname)}"

    # Check if host already exists
    check = await _ssh_run(f"test -f {cfg_file} && echo EXISTS")
    if "EXISTS" in (check.stdout or ""):
        raise ValueError(f"Config file already exists: {cfg_file}")

    # Generate config
    config_content = generate_host_config(hostname, alias, address, hostgroup, services)

    # Write the config file
    # Escape single quotes in content for shell
    escaped = config_content.replace("'", "'\\''")
    write_result = await _ssh_run(f"echo '{escaped}' > {cfg_file}")
    if write_result.exit_status != 0:
        raise RuntimeError(f"Failed to write config: {write_result.stderr}")

    # Validate
    valid, output = await validate_config()
    if not valid:
        # Rollback: remove the new file
        await _ssh_run(f"rm -f {cfg_file}")
        logger.error("nagios_add_host_validation_failed", hostname=hostname)
        raise ValueError(f"Config validation failed, rolled back. Output:\n{output}")

    # Reload
    reloaded, reload_output = await reload_nagios()
    if not reloaded:
        logger.warning("nagios_reload_failed_after_add", hostname=hostname)

    # Invalidate cache so next read picks up the new host
    global _cache_ts
    _cache_ts = 0

    logger.info("nagios_host_added", hostname=hostname, cfg_file=cfg_file)
    return {
        "status": "created",
        "hostname": hostname,
        "cfg_file": cfg_file,
        "reload": "ok" if reloaded else "failed",
    }


async def edit_host(
    hostname: str,
    alias: str | None = None,
    address: str | None = None,
    hostgroup: str | None = None,
    services: list[ServiceDef] | None = None,
) -> dict[str, Any]:
    """Edit an existing host's config. Backs up before modifying."""
    cfg_file = f"{CONFIG_DIR}/{_cfg_filename(hostname)}"

    # Check exists
    check = await _ssh_run(f"test -f {cfg_file} && echo EXISTS")
    if "EXISTS" not in (check.stdout or ""):
        # Try to find by hostname in any cfg file
        find = await _ssh_run(
            f"grep -rl 'host_name.*{hostname}' {CONFIG_DIR}/ 2>/dev/null | head -1"
        )
        found_file = (find.stdout or "").strip()
        if found_file:
            cfg_file = found_file
        else:
            raise ValueError(f"No config found for host: {hostname}")

    # Backup existing
    ts = int(time.time())
    backup_file = f"{cfg_file}.bak.{ts}"
    await _ssh_run(f"cp {cfg_file} {backup_file}")

    # Read current config to get existing values if not overridden
    current = await _ssh_run(f"cat {cfg_file}")
    current_content = current.stdout or ""

    # Parse current host values from the config
    current_alias = alias
    current_address = address
    current_hostgroup = hostgroup

    if current_alias is None:
        m = re.search(r"alias\s+(.+)", current_content)
        current_alias = m.group(1).strip() if m else hostname

    if current_address is None:
        m = re.search(r"address\s+(.+)", current_content)
        current_address = m.group(1).strip() if m else hostname

    if current_hostgroup is None:
        m = re.search(r"hostgroups?\s+(.+)", current_content)
        current_hostgroup = m.group(1).strip() if m else "pbx"

    # Generate new config
    config_content = generate_host_config(
        hostname, current_alias, current_address, current_hostgroup, services
    )

    # Write
    escaped = config_content.replace("'", "'\\''")
    await _ssh_run(f"echo '{escaped}' > {cfg_file}")

    # Validate
    valid, output = await validate_config()
    if not valid:
        # Rollback from backup
        await _ssh_run(f"cp {backup_file} {cfg_file}")
        await _ssh_run(f"rm -f {backup_file}")
        logger.error("nagios_edit_host_validation_failed", hostname=hostname)
        raise ValueError(f"Config validation failed, rolled back. Output:\n{output}")

    # Remove backup on success
    await _ssh_run(f"rm -f {backup_file}")

    # Reload
    reloaded, _ = await reload_nagios()

    global _cache_ts
    _cache_ts = 0

    logger.info("nagios_host_edited", hostname=hostname)
    return {
        "status": "updated",
        "hostname": hostname,
        "cfg_file": cfg_file,
        "reload": "ok" if reloaded else "failed",
    }


async def delete_host(hostname: str) -> dict[str, Any]:
    """Delete a host from Nagios. Backs up before removing."""
    cfg_file = f"{CONFIG_DIR}/{_cfg_filename(hostname)}"

    # Find the config file
    check = await _ssh_run(f"test -f {cfg_file} && echo EXISTS")
    if "EXISTS" not in (check.stdout or ""):
        # Try to find by hostname
        find = await _ssh_run(
            f"grep -rl 'host_name.*{hostname}' {CONFIG_DIR}/ 2>/dev/null | head -1"
        )
        found_file = (find.stdout or "").strip()
        if found_file:
            cfg_file = found_file
        else:
            raise ValueError(f"No config found for host: {hostname}")

    # Backup
    ts = int(time.time())
    backup_file = f"{cfg_file}.bak.{ts}"
    await _ssh_run(f"cp {cfg_file} {backup_file}")

    # Remove the config
    await _ssh_run(f"rm -f {cfg_file}")

    # Validate
    valid, output = await validate_config()
    if not valid:
        # Rollback: restore from backup
        await _ssh_run(f"cp {backup_file} {cfg_file}")
        await _ssh_run(f"rm -f {backup_file}")
        logger.error("nagios_delete_host_validation_failed", hostname=hostname)
        raise ValueError(f"Config validation failed, rolled back. Output:\n{output}")

    # Reload
    reloaded, _ = await reload_nagios()

    global _cache_ts
    _cache_ts = 0

    logger.info("nagios_host_deleted", hostname=hostname, cfg_file=cfg_file)
    return {
        "status": "deleted",
        "hostname": hostname,
        "cfg_file": cfg_file,
        "backup": backup_file,
        "reload": "ok" if reloaded else "failed",
    }


async def get_host_config(hostname: str) -> str:
    """Read the raw config file for a host."""
    cfg_file = f"{CONFIG_DIR}/{_cfg_filename(hostname)}"

    check = await _ssh_run(f"test -f {cfg_file} && echo EXISTS")
    if "EXISTS" not in (check.stdout or ""):
        find = await _ssh_run(
            f"grep -rl 'host_name.*{hostname}' {CONFIG_DIR}/ 2>/dev/null | head -1"
        )
        found_file = (find.stdout or "").strip()
        if found_file:
            cfg_file = found_file
        else:
            raise ValueError(f"No config found for host: {hostname}")

    result = await _ssh_run(f"cat {cfg_file}")
    return result.stdout or ""
