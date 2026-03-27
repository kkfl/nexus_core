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
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if "BEGIN OPENSSH PRIVATE KEY" in pem or "BEGIN RSA PRIVATE KEY" in pem or "BEGIN PRIVATE KEY" in pem:
        pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(pem))
        ssh.connect(host, port=port, username=username, pkey=pkey, timeout=10)
    else:
        # Fallback to using the secret as a password
        ssh.connect(host, port=port, username=username, password=pem, timeout=10)
    return ssh


# ---------------------------------------------------------------------------
# Human-readable error messages for common SSH bridge failures
# ---------------------------------------------------------------------------

_SCRIPT_ERROR_HINTS: dict[str, dict[int, str]] = {
    "create_mailbox": {
        1: "Mailbox creation failed. The domain may not be hosted on this mail server, "
        "or the mailbox may already exist. Only domains configured in iRedMail are allowed.",
        2: "Permission denied on mail server. Check SSH bridge credentials.",
        126: "Mail admin script is not executable on the server.",
        127: "Mail admin script not found on the server.",
    },
    "set_password": {
        1: "Password reset failed. The mailbox may not exist on this mail server.",
        2: "Permission denied on mail server.",
    },
    "disable_mailbox": {
        1: "Disable failed. The mailbox may not exist.",
    },
}

_GENERIC_EXIT_HINTS: dict[int, str] = {
    1: "The command failed on the mail server.",
    2: "Permission denied on the remote server.",
    126: "Script is not executable.",
    127: "Script not found on the remote server.",
    255: "SSH connection failed or was refused.",
}


def _describe_error(script: str, exit_code: int, stderr_text: str, args: list[str] | None) -> str:
    """Build a human-readable error message from script context."""
    # If the remote script wrote useful stderr, use it
    if stderr_text and "exit code" not in stderr_text.lower():
        return stderr_text[:500]

    # Try script-specific hint
    script_hints = _SCRIPT_ERROR_HINTS.get(script, {})
    hint = script_hints.get(exit_code)

    # Fall back to generic hint
    if not hint:
        hint = _GENERIC_EXIT_HINTS.get(exit_code, f"Unexpected error (exit code {exit_code}).")

    # Enrich with context from args (e.g. show the email/domain)
    if args and script in ("create_mailbox", "set_password", "disable_mailbox"):
        email = args[0] if args else ""
        if "@" in email:
            domain = email.split("@", 1)[1]
            hint += f" (email: {email}, domain: {domain})"

    return hint


def _sync_bridge(host, port, username, pem, script, args, cmd_timeout):
    """Run a bridge command synchronously (runs in thread)."""
    cmd_parts = [f"sudo /opt/nexus-mail-admin/{script}"]
    if args:
        for a in args:
            safe = a.replace("'", "'\\''")
            cmd_parts.append(f"'{safe}'")
    cmd = " ".join(cmd_parts)

    ssh = _build_ssh_client(host, port, username, pem)
    try:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=cmd_timeout)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        exit_code = stdout.channel.recv_exit_status()

        if exit_code != 0:
            return {"ok": False, "error": _describe_error(script, exit_code, err, args)}

        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"Invalid response from mail server: {out[:200]}"}
    finally:
        ssh.close()


async def run_bridge_command(script: str, args: list[str] | None = None, timeout: int = 15) -> dict:
    """
    Run a nexus-mail-admin script via sudo on mx.
    Returns parsed JSON from stdout.
    """
    host = await vault.get_secret("ssh.iredmail.host")
    port = int(await vault.get_secret("ssh.iredmail.port"))
    username = await vault.get_secret("ssh.iredmail.username")
    pem = await vault.get_secret("ssh.iredmail.private_key_pem")

    logger.info("ssh_bridge_exec", script=script, args_count=len(args or []))
    return await asyncio.to_thread(_sync_bridge, host, port, username, pem, script, args, timeout)


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
