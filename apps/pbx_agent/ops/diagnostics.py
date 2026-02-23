"""
PBX diagnostics operations.
Implements: ping, ami-check, version
These are synchronous (immediate) — no job queue needed.
"""

import os
import re
from typing import Any

from apps.pbx_agent.adapters.ami import (
    AmiAuthError,
    AmiError,
    AmiTimeoutError,
    check_connectivity,
    run_ami_command,
)
from apps.pbx_agent.config import config

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")


def _load_fixture(name: str) -> str:
    path = os.path.join(FIXTURES_DIR, f"{name}.txt")
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return f"Mock output for {name}"


async def diagnostic_ping(host: str, port: int) -> dict[str, Any]:
    """TCP connectivity check to the AMI port."""
    if config.pbx_mock:
        return {"reachable": True, "host": host, "port": port, "latency_ms": 1}

    import time

    start = time.monotonic()
    reachable = await check_connectivity(host, port, timeout=5.0)
    latency_ms = int((time.monotonic() - start) * 1000)
    return {"reachable": reachable, "host": host, "port": port, "latency_ms": latency_ms}


async def diagnostic_ami_check(
    host: str, port: int, ami_username: str, ami_secret: str
) -> dict[str, Any]:
    """
    Attempt AMI login + logoff to validate credentials.
    Returns auth_ok=True/False without exposing secret.
    """
    if config.pbx_mock:
        return {"auth_ok": True, "host": host, "port": port, "ami_username": ami_username}

    try:
        # Run a benign command to confirm auth
        out = await run_ami_command(host, port, ami_username, ami_secret, "core show uptime")
        return {
            "auth_ok": True,
            "host": host,
            "port": port,
            "ami_username": ami_username,
            "output_snippet": out[:100],
        }
    except AmiAuthError as e:
        return {"auth_ok": False, "reason": str(e), "host": host}
    except AmiTimeoutError:
        return {"auth_ok": False, "reason": "timeout", "host": host}
    except AmiError:
        return {"auth_ok": False, "reason": "connection_error", "host": host}


async def diagnostic_version(
    host: str, port: int, ami_username: str, ami_secret: str
) -> dict[str, Any]:
    """Get Asterisk + FreePBX version info."""
    if config.pbx_mock:
        return {
            "asterisk_version": "Asterisk 20.3.0",
            "system_name": "FreePBX 16 (mock)",
            "uptime": _load_fixture("core_show_uptime"),
        }

    out = await run_ami_command(host, port, ami_username, ami_secret, "core show version")
    uptime = await run_ami_command(host, port, ami_username, ami_secret, "core show uptime")

    version_match = re.search(r"Asterisk\s+([\d.]+)", out)
    version = version_match.group(0) if version_match else "unknown"
    return {
        "asterisk_version": version,
        "version_output": out[:300],
        "uptime_output": uptime[:300],
    }
