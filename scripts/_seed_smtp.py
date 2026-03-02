"""
Reset alerts@gsmcall.com password in iRedMail and seed SMTP secrets into vault.
"""

import secrets
import string

import paramiko

# ---------- Config ----------
HOST = "mx.gsmcall.com"
SSH_PORT = 2007
SSH_USER = "root"
SSH_PASS = "G$Mcall01"

VAULT_BASE = "http://localhost:8007"
VAULT_H = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": "nexus-internal-key",
    "Content-Type": "application/json",
}

MAILBOX = "alerts@gsmcall.com"


def generate_password(length=24):
    alphabet = string.ascii_letters + string.digits + "!@#%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def run_ssh(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err


def main():
    # Generate strong password
    new_pass = generate_password()
    print(f"Generated new password for {MAILBOX} (len={len(new_pass)})")
    # DO NOT print the password

    # Connect to mail server
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOST}:{SSH_PORT}...")
    ssh.connect(HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS, timeout=10)
    print("Connected!")

    # iRedMail uses doveadm to generate password hashes
    # Check what scheme is used
    out, err = run_ssh(ssh, "doveadm pw -s SSHA512 -p 'test123' | head -1")
    print(f"Password scheme test: {'OK' if out.startswith('{SSHA512}') else 'UNEXPECTED'}")

    # Generate the hash for the new password (escape single quotes)
    safe_pass = new_pass.replace("'", "'\\''")
    out, err = run_ssh(ssh, f"doveadm pw -s SSHA512 -p '{safe_pass}'")
    if not out.startswith("{SSHA512}"):
        print(f"ERROR: unexpected hash output: {out[:50]}")
        ssh.close()
        return
    pw_hash = out.strip()
    print("Password hash generated (SSHA512)")

    # Update in MySQL
    escaped_hash = pw_hash.replace("'", "\\'")
    update_sql = f"UPDATE mailbox SET password='{escaped_hash}' WHERE username='{MAILBOX}';"
    out, err = run_ssh(ssh, f'mysql -u root vmail -e "{update_sql}"')
    if err:
        print(f"MySQL error: {err}")
        ssh.close()
        return
    print(f"Password updated in MySQL for {MAILBOX}")

    # Verify the update took
    out, err = run_ssh(
        ssh,
        f"mysql -u root vmail -e \"SELECT username, LEFT(password,20) as pw_prefix FROM mailbox WHERE username='{MAILBOX}';\"",
    )
    print(f"Verification: {out}")

    ssh.close()
    print("SSH session closed")

    # Now seed SMTP secrets into vault
    print("\n=== Seeding SMTP secrets into vault ===")
    smtp_secrets = {
        "smtp.host": HOST,
        "smtp.port": "587",
        "smtp.username": MAILBOX,
        "smtp.password": new_pass,
        "smtp.from_address": MAILBOX,
    }

    import httpx as hx

    for alias, value in smtp_secrets.items():
        # Check if already exists
        resp = hx.get(
            f"{VAULT_BASE}/v1/secrets",
            params={"tenant_id": "nexus", "env": "prod"},
            headers=VAULT_H,
        )
        existing = next((s for s in resp.json() if s["alias"] == alias), None)

        if existing:
            # Rotate existing secret
            rotate_resp = hx.post(
                f"{VAULT_BASE}/v1/secrets/{existing['id']}/rotate",
                json={"new_value": value, "reason": "iredmail_smtp_setup"},
                headers=VAULT_H,
            )
            if rotate_resp.status_code == 200:
                print(f"  ROTATED: {alias}")
            else:
                print(
                    f"  ROTATE FAIL ({alias}): {rotate_resp.status_code} {rotate_resp.text[:100]}"
                )
        else:
            # Create new secret
            create_resp = hx.post(
                f"{VAULT_BASE}/v1/secrets",
                json={
                    "alias": alias,
                    "value": value,
                    "tenant_id": "nexus",
                    "env": "prod",
                    "description": f"SMTP credential for mx.gsmcall.com ({alias})",
                },
                headers=VAULT_H,
            )
            if create_resp.status_code == 201:
                print(f"  CREATED: {alias}")
            else:
                print(
                    f"  CREATE FAIL ({alias}): {create_resp.status_code} {create_resp.text[:100]}"
                )

    print("\n=== SMTP secrets seeded ===")


if __name__ == "__main__":
    main()
