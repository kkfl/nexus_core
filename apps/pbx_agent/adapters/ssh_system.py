"""
SSH-based system metrics adapter for PBX nodes.

Connects via SSH (key or password) and runs standard Linux + Asterisk CLI
commands to collect system resource usage and PBX status.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

CONNECT_TIMEOUT = 8
CMD_TIMEOUT = 10


@dataclass
class SystemMetrics:
    cpu_pct: float | None = None
    ram_used_mb: int | None = None
    ram_total_mb: int | None = None
    ram_pct: float | None = None
    disk_used_gb: float | None = None
    disk_total_gb: float | None = None
    disk_pct: float | None = None


@dataclass
class AsteriskCliStatus:
    asterisk_up: bool = False
    version: str | None = None
    active_calls: int = 0
    active_channels: int = 0
    sip_registrations: int = 0
    calls_processed: int = 0  # from "core show channels count"
    uptime_seconds: int = 0
    uptime_human: str | None = None
    calls_24h: int = 0


@dataclass
class PbxNodeSnapshot:
    """Combined SSH-gathered snapshot of a PBX node."""

    online: bool = False
    ssh_ok: bool = False
    system: SystemMetrics = field(default_factory=SystemMetrics)
    asterisk: AsteriskCliStatus = field(default_factory=AsteriskCliStatus)
    error: str | None = None


def _get_ssh_client(host: str, port: int, username: str,
                    private_key_pem: str | None = None,
                    password: str | None = None):
    """Create and connect a paramiko SSH client. Returns the client."""
    import paramiko

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    kwargs: dict = {
        "hostname": host,
        "port": port,
        "username": username,
        "timeout": CONNECT_TIMEOUT,
    }

    if private_key_pem:
        # Try Ed25519 first, then RSA
        key_obj = None
        for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                key_obj = cls.from_private_key(io.StringIO(private_key_pem))
                break
            except Exception:
                continue
        if key_obj:
            kwargs["pkey"] = key_obj
        elif password:
            kwargs["password"] = password
        else:
            raise ValueError("SSH key provided but could not parse; no password fallback")
    elif password:
        kwargs["password"] = password
    else:
        raise ValueError("No SSH key or password provided")

    ssh.connect(**kwargs)
    return ssh


def _run_cmd(ssh, cmd: str, timeout: int = CMD_TIMEOUT) -> str:
    """Run a command and return stdout. Non-blocking for the caller."""
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode("utf-8", errors="replace").strip()


def _parse_system_metrics(ssh) -> SystemMetrics:
    """Collect CPU, RAM, Disk via standard Linux tools."""
    m = SystemMetrics()

    # CPU — from /proc/stat or top
    try:
        raw = _run_cmd(ssh,
            "grep 'cpu ' /proc/stat | awk '{u=$2+$4; t=$2+$4+$5; printf \"%.1f\", u/t*100}'",
            timeout=5)
        if raw:
            m.cpu_pct = round(float(raw), 1)
    except Exception:
        pass

    # RAM — from free -m
    try:
        raw = _run_cmd(ssh, "free -m | awk 'NR==2{printf \"%d %d\", $3, $2}'", timeout=5)
        if raw:
            parts = raw.split()
            if len(parts) >= 2:
                m.ram_used_mb = int(parts[0])
                m.ram_total_mb = int(parts[1])
                if m.ram_total_mb > 0:
                    m.ram_pct = round(m.ram_used_mb / m.ram_total_mb * 100, 1)
    except Exception:
        pass

    # Disk — root partition
    try:
        raw = _run_cmd(ssh,
            "df -BG / | awk 'NR==2{gsub(/G/,\"\",$2); gsub(/G/,\"\",$3); printf \"%s %s\", $3, $2}'",
            timeout=5)
        if raw:
            parts = raw.split()
            if len(parts) >= 2:
                m.disk_used_gb = float(parts[0])
                m.disk_total_gb = float(parts[1])
                if m.disk_total_gb > 0:
                    m.disk_pct = round(m.disk_used_gb / m.disk_total_gb * 100, 1)
    except Exception:
        pass

    return m


def _parse_asterisk_status(ssh) -> AsteriskCliStatus:
    """Collect Asterisk status via CLI commands over SSH."""
    a = AsteriskCliStatus()

    # Check if Asterisk is running
    try:
        raw = _run_cmd(ssh, "pgrep -c asterisk 2>/dev/null || echo 0", timeout=3)
        a.asterisk_up = int(raw or "0") > 0
    except Exception:
        a.asterisk_up = False

    if not a.asterisk_up:
        return a

    # Version
    try:
        raw = _run_cmd(ssh, "asterisk -rx 'core show version' 2>/dev/null | head -1", timeout=5)
        if raw and "Asterisk" in raw:
            a.version = raw.split("Asterisk ")[1].split(" ")[0] if "Asterisk " in raw else raw[:60]
    except Exception:
        pass

    # Active channels / calls
    try:
        raw = _run_cmd(ssh, "asterisk -rx 'core show channels count' 2>/dev/null", timeout=5)
        if raw:
            for line in raw.split("\n"):
                if "active call" in line.lower():
                    nums = re.findall(r"(\d+)", line)
                    if nums:
                        a.active_calls = int(nums[0])
                elif "active channel" in line.lower():
                    nums = re.findall(r"(\d+)", line)
                    if nums:
                        a.active_channels = int(nums[0])
                elif "calls processed" in line.lower():
                    nums = re.findall(r"(\d+)", line)
                    if nums:
                        a.calls_processed = int(nums[0])
    except Exception:
        pass

    # SIP registrations (try pjsip first, fall back to sip)
    try:
        raw = _run_cmd(ssh,
            "asterisk -rx 'pjsip show registrations' 2>/dev/null || "
            "asterisk -rx 'sip show registry' 2>/dev/null",
            timeout=5)
        if raw:
            # Count non-header, non-empty lines with "Registered" or valid entries
            lines = [l for l in raw.split("\n")
                     if l.strip() and not l.startswith("=") and not l.startswith("-")
                     and "Object" not in l and "Name/username" not in l]
            a.sip_registrations = max(0, len(lines) - 1)  # subtract header
    except Exception:
        pass

    # Uptime
    try:
        raw = _run_cmd(ssh, "asterisk -rx 'core show uptime' 2>/dev/null", timeout=5)
        if raw:
            a.uptime_human = raw.strip()
            # Parse seconds from patterns like "2 weeks, 3 days, 14 hours"
            total = 0
            for val, unit in re.findall(r"(\d+)\s+(week|day|hour|minute|second)", raw, re.I):
                n = int(val)
                if "week" in unit.lower():
                    total += n * 604800
                elif "day" in unit.lower():
                    total += n * 86400
                elif "hour" in unit.lower():
                    total += n * 3600
                elif "minute" in unit.lower():
                    total += n * 60
                else:
                    total += n
            a.uptime_seconds = total
    except Exception:
        pass

    # Calls in last 24h from CDR database (if available)
    try:
        raw = _run_cmd(ssh,
            "mysql -N -e \"SELECT COUNT(*) FROM asteriskcdrdb.cdr "
            "WHERE calldate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)\" 2>/dev/null || echo 0",
            timeout=5)
        if raw and raw.isdigit():
            a.calls_24h = int(raw)
    except Exception:
        a.calls_24h = 0

    return a


async def collect_node_snapshot(
    host: str,
    port: int,
    username: str,
    private_key_pem: str | None = None,
    password: str | None = None,
) -> PbxNodeSnapshot:
    """
    Collect a full PBX node snapshot via SSH.
    Runs in a thread to avoid blocking the event loop.
    """
    def _collect():
        snap = PbxNodeSnapshot()
        try:
            ssh = _get_ssh_client(host, port, username, private_key_pem, password)
            snap.ssh_ok = True
            snap.online = True

            try:
                snap.system = _parse_system_metrics(ssh)
            except Exception as e:
                logger.warning("ssh_system_metrics_error", host=host, error=str(e)[:200])

            try:
                snap.asterisk = _parse_asterisk_status(ssh)
            except Exception as e:
                logger.warning("ssh_asterisk_status_error", host=host, error=str(e)[:200])

            ssh.close()
        except Exception as e:
            snap.error = f"{type(e).__name__}: {str(e)[:200]}"
            logger.warning("ssh_connect_error", host=host, port=port, error=snap.error)

        return snap

    return await asyncio.to_thread(_collect)


async def check_ssh_connectivity(host: str, port: int, timeout: float = 5.0) -> bool:
    """TCP ping — just proves the SSH port is open."""
    import socket
    def _check():
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return True
        except Exception:
            return False
    return await asyncio.to_thread(_check)
