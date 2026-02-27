"""
SSH bridge client — calls admin scripts on mx.gsmcall.com via paramiko.

All synchronous paramiko calls are wrapped in asyncio.to_thread()
to avoid blocking the uvicorn event loop.
"""

from __future__ import annotations

import asyncio
import io
import json

import paramiko
import structlog

from apps.email_agent.client import vault

logger = structlog.get_logger(__name__)


def _build_ssh_client(host, port, username, pem):
    """Build paramiko SSH client (synchronous, runs in thread)."""
    pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(pem))
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=username, pkey=pkey, timeout=10)
    return ssh


def _sync_bridge(host, port, username, pem, script, args):
    """Run a bridge command synchronously (runs in thread)."""
    cmd_parts = [f"sudo /opt/nexus-mail-admin/{script}"]
    if args:
        for a in args:
            safe = a.replace("'", "'\\''")
            cmd_parts.append(f"'{safe}'")
    cmd = " ".join(cmd_parts)

    ssh = _build_ssh_client(host, port, username, pem)
    try:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()

        if exit_code != 0:
            return {"ok": False, "error": err[:500] or f"exit code {exit_code}"}

        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"Invalid JSON: {out[:200]}"}
    finally:
        ssh.close()


async def run_bridge_command(script: str, args: list[str] | None = None) -> dict:
    """
    Run a nexus-mail-admin script via sudo on mx.
    Returns parsed JSON from stdout.
    """
    host = await vault.get_secret("ssh.iredmail.host")
    port = int(await vault.get_secret("ssh.iredmail.port"))
    username = await vault.get_secret("ssh.iredmail.username")
    pem = await vault.get_secret("ssh.iredmail.private_key_pem")

    logger.info("ssh_bridge_exec", script=script, args_count=len(args or []))
    return await asyncio.to_thread(_sync_bridge, host, port, username, pem, script, args)


def _sync_ssh_check(host, port, username, pem):
    """Quick SSH check (runs in thread)."""
    ssh = _build_ssh_client(host, port, username, pem)
    stdin, stdout, stderr = ssh.exec_command("echo ok", timeout=5)
    result = stdout.read().decode().strip()
    ssh.close()
    return result == "ok", "connected"


async def check_ssh_connectivity() -> tuple[bool, str]:
    """Quick connectivity check — returns (ok, detail)."""
    try:
        host = await vault.get_secret("ssh.iredmail.host")
        port = int(await vault.get_secret("ssh.iredmail.port"))
        username = await vault.get_secret("ssh.iredmail.username")
        pem = await vault.get_secret("ssh.iredmail.private_key_pem")
        return await asyncio.to_thread(_sync_ssh_check, host, port, username, pem)
    except Exception as e:
        return False, str(e)[:200]
