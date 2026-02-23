"""
PBX status query operations (read-only, real-time via AMI).
Implements: peers, registrations, channels, uptime
"""
import os
import re
from typing import Any, Dict, List

from apps.pbx_agent.adapters.ami import run_ami_command
from apps.pbx_agent.config import config

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")


def _load_fixture(name: str) -> str:
    path = os.path.join(FIXTURES_DIR, f"{name}.txt")
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return f"Mock output for {name}"


async def status_peers(host: str, port: int, username: str, secret: str) -> Dict[str, Any]:
    """PJSIP endpoint status summary."""
    if config.pbx_mock:
        raw = _load_fixture("pjsip_show_endpoints")
    else:
        raw = await run_ami_command(host, port, username, secret, "pjsip show endpoints")

    endpoints = re.findall(r'Endpoint:\s+([^\s/]+)', raw)
    # Try chan_sip fallback
    if not endpoints:
        if not config.pbx_mock:
            raw = await run_ami_command(host, port, username, secret, "sip show peers")
        peers = re.findall(r'^(\S+)\s+\d+\.\d+\.\d+\.\d+', raw, re.MULTILINE)
        return {"driver": "chan_sip", "count": len(peers), "peers": peers[:50], "raw": raw[:500]}

    return {"driver": "pjsip", "count": len(endpoints), "endpoints": endpoints[:50], "raw": raw[:500]}


async def status_registrations(host: str, port: int, username: str, secret: str) -> Dict[str, Any]:
    """SIP provider registration status."""
    if config.pbx_mock:
        raw = _load_fixture("pjsip_show_registrations")
    else:
        raw = await run_ami_command(host, port, username, secret, "pjsip show registrations")

    # Parse Registration: <contact> <status>
    regs = re.findall(r'(Registered|Rejected|Unregistered|Failed)', raw, re.IGNORECASE)
    counts = {}
    for r in regs:
        counts[r.lower()] = counts.get(r.lower(), 0) + 1

    return {"registration_counts": counts, "total": len(regs), "raw": raw[:500]}


async def status_channels(host: str, port: int, username: str, secret: str) -> Dict[str, Any]:
    """Active channel count and brief summary."""
    if config.pbx_mock:
        raw = _load_fixture("core_show_channels_concise")
    else:
        raw = await run_ami_command(host, port, username, secret, "core show channels concise")

    # Concise format: each live channel line contains "!"
    lines = [l for l in raw.split('\n') if '!' in l]
    return {
        "active_channels": len(lines),
        "channel_lines": lines[:20],
        "raw": raw[:500],
    }


async def status_uptime(host: str, port: int, username: str, secret: str) -> Dict[str, Any]:
    """Core uptime."""
    if config.pbx_mock:
        raw = _load_fixture("core_show_uptime")
    else:
        raw = await run_ami_command(host, port, username, secret, "core show uptime")

    # Parse "System uptime: X hours, Y minutes, Z seconds"
    m = re.search(r'System uptime:\s*(.+)', raw)
    uptime_str = m.group(1).strip() if m else "unknown"
    return {"uptime": uptime_str, "raw": raw[:300]}
