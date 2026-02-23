"""
Production AMI (Asterisk Manager Interface) adapter.

Design principles (per RTC/Telephony KI):
- One connection per operation: AMI is TCP/line-protocol; we open, auth, run, logoff, close.
  Connection pooling would require AMI keepalives + event filtering — deferred to V2.
- Timeouts at every await: AMI can hang silently on dead connections.
- All secret values are passed-in parameters, never stored or logged by this module.
- Output is passed through redaction before returning.

AMI protocol overview:
  Client sends key: value\\r\\n blocks terminated by \\r\\n
  Server responds with key: value\\r\\n blocks terminated by \\r\\n\\r\\n (double CRLF)
  Command responses end with Output: ...\\r\\n--END COMMAND--\\r\\n
"""
import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

import structlog

from apps.pbx_agent.redaction.logs import redact

logger = structlog.get_logger(__name__)

# Timeouts
CONNECT_TIMEOUT = 5.0
AUTH_TIMEOUT = 5.0
CMD_TIMEOUT = 15.0
READ_CHUNK = 4096


class AmiError(Exception):
    pass


class AmiAuthError(AmiError):
    pass


class AmiTimeoutError(AmiError):
    pass


async def _read_response(reader: asyncio.StreamReader, timeout: float = CMD_TIMEOUT) -> str:
    """Read AMI response blocks until double CRLF terminator."""
    buf = b""
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(READ_CHUNK), timeout=timeout)
            if not chunk:
                break
            buf += chunk
            # AMI responses terminate with \r\n\r\n
            if b"\r\n\r\n" in buf:
                break
    except asyncio.TimeoutError:
        raise AmiTimeoutError("Timed out reading AMI response")
    return buf.decode("utf-8", errors="replace")


async def _read_command_output(reader: asyncio.StreamReader, timeout: float = CMD_TIMEOUT) -> str:
    """Read AMI Action: Command response until --END COMMAND-- marker."""
    buf = b""
    try:
        while b"--END COMMAND--" not in buf and b"Response: Error" not in buf:
            chunk = await asyncio.wait_for(reader.read(READ_CHUNK), timeout=timeout)
            if not chunk:
                break
            buf += chunk
    except asyncio.TimeoutError:
        raise AmiTimeoutError("Timed out reading AMI command output")
    return buf.decode("utf-8", errors="replace")


async def _ami_connect(
    host: str, port: int, username: str, secret: str
) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Open TCP connection and authenticate with AMI."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=CONNECT_TIMEOUT
        )
    except asyncio.TimeoutError:
        raise AmiTimeoutError(f"Connection to {host}:{port} timed out")
    except OSError as e:
        raise AmiError(f"Cannot connect to {host}:{port}: {type(e).__name__}") from None

    # Read AMI banner (e.g. "Asterisk Call Manager/5.0.0")
    try:
        banner = await asyncio.wait_for(reader.readline(), timeout=AUTH_TIMEOUT)
    except asyncio.TimeoutError:
        writer.close()
        raise AmiTimeoutError("Timed out reading AMI banner")

    # Login — secret is NEVER logged
    login = f"Action: Login\r\nUsername: {username}\r\nSecret: {secret}\r\n\r\n"
    writer.write(login.encode())
    await writer.drain()

    auth_resp = await _read_response(reader, timeout=AUTH_TIMEOUT)

    if "Authentication accepted" not in auth_resp:
        writer.close()
        # Do not include the response in error (could contain hints)
        raise AmiAuthError(f"AMI authentication failed for user '{username}' on {host}:{port}")

    return reader, writer


async def _ami_logoff(writer: asyncio.StreamWriter) -> None:
    try:
        writer.write(b"Action: Logoff\r\n\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass  # Best-effort cleanup


async def run_ami_command(
    host: str,
    port: int,
    username: str,
    secret: str,
    command: str,
) -> str:
    """
    Connect to AMI, authenticate, run a CLI command via Action: Command,
    logoff, and return the redacted output.
    """
    logger.debug("ami_command_start", host=host, port=port, username=username, command=command)
    reader, writer = await _ami_connect(host, port, username, secret)
    try:
        action = f"Action: Command\r\nCommand: {command}\r\n\r\n"
        writer.write(action.encode())
        await writer.drain()
        raw = await _read_command_output(reader, timeout=CMD_TIMEOUT)
        output = redact(raw)
        logger.debug("ami_command_complete", command=command, output_len=len(output))
        return output
    finally:
        await _ami_logoff(writer)


async def run_ami_action(
    host: str,
    port: int,
    username: str,
    secret: str,
    action_name: str,
    fields: Optional[Dict[str, str]] = None,
) -> str:
    """
    Run a structured AMI Action (not a CLI command).
    Returns the raw response block (redacted).
    """
    reader, writer = await _ami_connect(host, port, username, secret)
    try:
        parts = [f"Action: {action_name}\r\n"]
        if fields:
            for k, v in fields.items():
                parts.append(f"{k}: {v}\r\n")
        parts.append("\r\n")
        writer.write("".join(parts).encode())
        await writer.drain()
        raw = await _read_response(reader, timeout=CMD_TIMEOUT)
        return redact(raw)
    finally:
        await _ami_logoff(writer)


async def check_connectivity(host: str, port: int, timeout: float = 5.0) -> bool:
    """TCP ping — just proves the port is open (no auth)."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def parse_ami_response(raw: str) -> List[Dict[str, str]]:
    """
    Parse an AMI response string into a list of key-value dicts.
    Each block is separated by \\r\\n\\r\\n.
    """
    blocks = re.split(r'\r?\n\r?\n', raw.strip())
    result = []
    for block in blocks:
        if not block.strip():
            continue
        d: Dict[str, str] = {}
        for line in block.split("\n"):
            if ": " in line:
                k, _, v = line.partition(": ")
                d[k.strip()] = v.strip()
        if d:
            result.append(d)
    return result
