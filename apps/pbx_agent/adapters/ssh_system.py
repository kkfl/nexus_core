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


def sanitize_ssh_key(pem: str) -> str:
    """
    Sanitize an SSH private key value:
    - Strips carriage returns and trailing whitespace
    - Detects PuTTY PPK format and converts to OpenSSH PEM
    - If raw base64 (no PEM headers), auto-wraps with OPENSSH PRIVATE KEY headers
    """
    import base64
    import textwrap as tw

    # Clean up whitespace
    pem = pem.strip().replace('\r\n', '\n').replace('\r', '')

    # ── PPK format detection ──────────────────────────────────────────
    if pem.startswith('PuTTY-User-Key-File-'):
        return _convert_ppk_to_openssh(pem)

    # ── Already has PEM headers ───────────────────────────────────────
    if '-----BEGIN' in pem:
        return pem

    # ── Raw base64 detection ──────────────────────────────────────────
    clean = pem.replace('\n', '').replace(' ', '')
    try:
        decoded = base64.b64decode(clean)
        if decoded[:14] == b'openssh-key-v1':
            lines = tw.wrap(clean, 70)
            return '-----BEGIN OPENSSH PRIVATE KEY-----\n' + '\n'.join(lines) + '\n-----END OPENSSH PRIVATE KEY-----\n'
        if decoded[0:1] == b'\x30':
            lines = tw.wrap(clean, 64)
            return '-----BEGIN RSA PRIVATE KEY-----\n' + '\n'.join(lines) + '\n-----END RSA PRIVATE KEY-----\n'
    except Exception:
        pass

    return pem


def _convert_ppk_to_openssh(ppk_content: str) -> str:
    """Convert PuTTY PPK v2/v3 format to OpenSSH PEM."""
    import base64
    from cryptography.hazmat.primitives.asymmetric import rsa, ed25519, ec
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, NoEncryption,
    )

    logger.info("ppk_conversion_start", length=len(ppk_content))

    lines = ppk_content.strip().splitlines()
    headers: dict[str, str] = {}
    section = None
    section_lines: dict[str, list[str]] = {}

    for line in lines:
        if line.startswith('PuTTY-User-Key-File-'):
            headers['version'] = line.split(':')[0].split('-')[-1]
            headers['key_type'] = line.split(':',1)[1].strip()
        elif line.startswith('Encryption:'):
            headers['encryption'] = line.split(':',1)[1].strip()
        elif line.startswith('Comment:'):
            headers['comment'] = line.split(':',1)[1].strip()
        elif line.startswith('Public-Lines:'):
            section = 'public'
            section_lines['public'] = []
        elif line.startswith('Private-Lines:'):
            section = 'private'
            section_lines['private'] = []
        elif line.startswith('Private-MAC:') or line.startswith('Private-Hash:'):
            section = None
        elif section:
            section_lines[section].append(line.strip())

    if headers.get('encryption', 'none') != 'none':
        raise ValueError("Encrypted PPK files are not supported — export without passphrase from PuTTYgen")

    if 'private' not in section_lines:
        raise ValueError("Could not find private key data in PPK file")

    pub_blob = base64.b64decode(''.join(section_lines.get('public', [])))
    priv_blob = base64.b64decode(''.join(section_lines['private']))
    key_type = headers.get('key_type', '')

    if key_type == 'ssh-rsa':
        pem = _ppk_rsa_to_pem(pub_blob, priv_blob)
    elif key_type == 'ssh-ed25519':
        pem = _ppk_ed25519_to_pem(priv_blob)
    else:
        raise ValueError(f"Unsupported PPK key type: {key_type}")

    logger.info("ppk_conversion_success", key_type=key_type)
    return pem


def _read_ssh_string(data: bytes, offset: int) -> tuple[bytes, int]:
    """Read a length-prefixed SSH string from a byte buffer."""
    import struct
    length = struct.unpack('>I', data[offset:offset+4])[0]
    value = data[offset+4:offset+4+length]
    return value, offset + 4 + length


def _ppk_rsa_to_pem(pub_blob: bytes, priv_blob: bytes) -> str:
    """Reconstruct RSA key from PPK public+private blobs."""
    from cryptography.hazmat.primitives.asymmetric.rsa import rsa_crt_dmp1, rsa_crt_dmq1, rsa_crt_iqmp, RSAPrivateNumbers, RSAPublicNumbers
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

    # Public blob: key_type(string) + e(mpint) + n(mpint)
    off = 0
    _, off = _read_ssh_string(pub_blob, off)  # skip key type
    e_bytes, off = _read_ssh_string(pub_blob, off)
    n_bytes, off = _read_ssh_string(pub_blob, off)
    e = int.from_bytes(e_bytes, 'big')
    n = int.from_bytes(n_bytes, 'big')

    # Private blob: d(mpint) + p(mpint) + q(mpint) + iqmp(mpint)
    off = 0
    d_bytes, off = _read_ssh_string(priv_blob, off)
    p_bytes, off = _read_ssh_string(priv_blob, off)
    q_bytes, off = _read_ssh_string(priv_blob, off)
    iqmp_bytes, off = _read_ssh_string(priv_blob, off)
    d = int.from_bytes(d_bytes, 'big')
    p = int.from_bytes(p_bytes, 'big')
    q = int.from_bytes(q_bytes, 'big')
    iqmp = int.from_bytes(iqmp_bytes, 'big')

    dmp1 = rsa_crt_dmp1(d, p)
    dmq1 = rsa_crt_dmq1(d, q)

    pub_numbers = RSAPublicNumbers(e, n)
    priv_numbers = RSAPrivateNumbers(p, q, d, dmp1, dmq1, iqmp, pub_numbers)
    key = priv_numbers.private_key()

    return key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()).decode()


def _ppk_ed25519_to_pem(priv_blob: bytes) -> str:
    """Reconstruct Ed25519 key from PPK private blob."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

    # Ed25519 private blob is just the 64-byte seed+public concatenation
    # or sometimes just 32-byte seed
    off = 0
    priv_bytes, _ = _read_ssh_string(priv_blob, off)
    if len(priv_bytes) == 64:
        seed = priv_bytes[:32]
    elif len(priv_bytes) == 32:
        seed = priv_bytes
    else:
        raise ValueError(f"Unexpected Ed25519 private key length: {len(priv_bytes)}")

    key = Ed25519PrivateKey.from_private_bytes(seed)
    return key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()).decode()


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
        # Sanitize: auto-add PEM headers if missing, strip bad whitespace
        private_key_pem = sanitize_ssh_key(private_key_pem)
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

    # SIP + PJSIP registrations (only 3-4 digit extensions)
    pjsip_count = 0
    sip_count = 0

    # PJSIP: count registered contacts for 3-4 digit endpoints
    # Output format:
    #   Contact:  <Aor/ContactUri     >  Hash    Status    RTT(ms)
    #  ====...
    #   201/sip:201@10.0.0.5:5060       abc123   Avail     12.345
    try:
        raw = _run_cmd(ssh,
            "asterisk -rx 'pjsip show contacts' 2>/dev/null",
            timeout=5)
        if raw:
            for line in raw.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                # Skip separator lines
                if stripped.startswith("=") or stripped.startswith("-"):
                    continue
                if "Objects found" in stripped:
                    continue
                # Skip the header line (contains <Aor/ or "Hash")
                if '<Aor' in stripped or 'Hash' in stripped:
                    continue
                # Data lines look like: "Contact:  201/sip:201@10.0.0.5  abc  Avail  12.3"
                # or just: "201/sip:201@10.0.0.5  abc  Avail  12.3"
                if 'Avail' not in line and 'NonQual' not in line:
                    continue
                # Strip "Contact:" prefix if present
                data = stripped
                if data.startswith("Contact:"):
                    data = data[len("Contact:"):].strip()
                # Now data looks like "201/sip:201@..."
                parts = data.split("/", 1)
                if parts:
                    aor = parts[0].strip()
                    if re.match(r'^\d{3,4}$', aor):
                        pjsip_count += 1
    except Exception:
        pass

    # SIP (chan_sip): count registered peers for 3-4 digit extensions
    # Output format:
    #  Name/username    Host         Dyn Forcerport Comedia  ACL Port  Status
    #  201/201          10.0.0.5      D  Auto (No)  No           5060 OK (12 ms)
    try:
        raw = _run_cmd(ssh,
            "asterisk -rx 'sip show peers' 2>/dev/null",
            timeout=5)
        if raw:
            for line in raw.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("Name") or stripped.startswith("-") or "peers" in stripped.lower():
                    continue
                # Must have OK status
                if 'OK' not in line:
                    continue
                parts = stripped.split("/", 1)
                if parts:
                    peer = parts[0].strip()
                    if re.match(r'^\d{3,4}$', peer):
                        sip_count += 1
    except Exception:
        pass

    a.sip_registrations = pjsip_count + sip_count

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
