"""
Seed SSH + IMAP secrets, create nexus-inbox@gsmcall.com mailbox.
"""

import os
from pathlib import Path

import httpx
import paramiko

VAULT_BASE = "http://localhost:8007"
VAULT_H = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": "nexus-internal-key",
    "Content-Type": "application/json",
}

MX_HOST = "mx.gsmcall.com"
MX_PORT = 2007


def seed_secret(alias: str, value: str, desc: str):
    """Create or rotate a vault secret."""
    resp = httpx.get(
        f"{VAULT_BASE}/v1/secrets",
        params={"tenant_id": "nexus", "env": "prod"},
        headers=VAULT_H,
    )
    existing = next((s for s in resp.json() if s["alias"] == alias), None)

    if existing:
        r = httpx.post(
            f"{VAULT_BASE}/v1/secrets/{existing['id']}/rotate",
            json={"new_value": value, "reason": "email_agent_setup"},
            headers=VAULT_H,
        )
        print(f"  ROTATED: {alias} ({r.status_code})")
    else:
        r = httpx.post(
            f"{VAULT_BASE}/v1/secrets",
            json={
                "alias": alias,
                "value": value,
                "tenant_id": "nexus",
                "env": "prod",
                "description": desc,
            },
            headers=VAULT_H,
        )
        print(f"  CREATED: {alias} ({r.status_code})")


def main():
    # --- Seed SSH secrets ---
    print("=== Seeding SSH secrets ===")
    key_path = os.path.join(os.environ["USERPROFILE"], ".ssh", "nexus_iredmail")
    pem = Path(key_path).read_text()

    seed_secret("ssh.iredmail.host", MX_HOST, "iRedMail SSH host")
    seed_secret("ssh.iredmail.port", str(MX_PORT), "iRedMail SSH port")
    seed_secret("ssh.iredmail.username", "nexusops", "iRedMail SSH user")
    seed_secret("ssh.iredmail.private_key_pem", pem.strip(), "iRedMail SSH private key")

    # --- Create nexus-inbox@gsmcall.com via bridge ---
    print("\n=== Creating nexus-inbox@gsmcall.com ===")
    key = paramiko.Ed25519Key.from_private_key_file(key_path)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(MX_HOST, port=MX_PORT, username="nexusops", pkey=key, timeout=10)

    import secrets
    import string

    inbox_pass = "".join(
        secrets.choice(string.ascii_letters + string.digits + "!@#%^") for _ in range(24)
    )

    stdin, stdout, stderr = ssh.exec_command(
        f"sudo /opt/nexus-mail-admin/create_mailbox 'nexus-inbox@gsmcall.com' '{inbox_pass}'"
    )
    print(f"  {stdout.read().decode().strip()}")

    ssh.close()

    # --- Seed IMAP secrets ---
    print("\n=== Seeding IMAP secrets ===")
    seed_secret("email.imap.host", MX_HOST, "IMAP host for ingest mailbox")
    seed_secret("email.imap.port", "993", "IMAP TLS port")
    seed_secret("email.imap.username", "nexus-inbox@gsmcall.com", "IMAP ingest mailbox")
    seed_secret("email.imap.password", inbox_pass, "IMAP ingest mailbox password")

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
