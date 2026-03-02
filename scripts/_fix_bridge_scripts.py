"""Deploy fixed create_mailbox and test it."""

import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("mx.gsmcall.com", port=2007, username="root", password="G$Mcall01", timeout=10)

script = r"""#!/bin/bash
# Create a new mailbox
# Usage: create_mailbox <email> <password>
set -euo pipefail

LOG="/var/log/nexus-mail-admin.log"
EMAIL="${1:-}"
PASS="${2:-}"

if [ -z "$EMAIL" ] || [ -z "$PASS" ]; then
    echo '{"ok":false,"error":"usage: create_mailbox <email> <password>"}'
    exit 1
fi

DOMAIN=$(echo "$EMAIL" | cut -d@ -f2)
LOCAL=$(echo "$EMAIL" | cut -d@ -f1)

# Check domain exists
DOMAIN_EXISTS=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e \
    "SELECT COUNT(*) FROM domain WHERE domain='$DOMAIN';" 2>/dev/null)

if [ "$DOMAIN_EXISTS" = "0" ]; then
    echo "{\"ok\":false,\"error\":\"domain '$DOMAIN' not found in mail system\"}"
    echo "$(date -Iseconds) create_mailbox FAIL domain_not_found email=$EMAIL" >> "$LOG"
    exit 1
fi

# Check if already exists
EXISTS=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e \
    "SELECT COUNT(*) FROM mailbox WHERE username='$EMAIL';" 2>/dev/null)

if [ "$EXISTS" != "0" ]; then
    echo "{\"ok\":true,\"email\":\"$EMAIL\",\"action\":\"already_exists\"}"
    echo "$(date -Iseconds) create_mailbox SKIP already_exists email=$EMAIL" >> "$LOG"
    exit 0
fi

# Generate password hash
SCHEME=$(doveconf -n 2>/dev/null | grep -oP 'default_pass_scheme\s*=\s*\K\S+' || echo 'SSHA512')
HASH=$(doveadm pw -s "$SCHEME" -p "$PASS")

# Maildir path: domain.tld/u/s/e/username-TIMESTAMP/
FIRST=$(echo "$LOCAL" | cut -c1)
SECOND=$(echo "$LOCAL" | cut -c2)
THIRD=$(echo "$LOCAL" | cut -c3)
TS=$(date +%Y.%m.%d.%H.%M.%S)
MAILDIR_PATH="$DOMAIN/$FIRST/$SECOND/$THIRD/$LOCAL-$TS/"

# Insert mailbox matching actual iRedMail schema
mysql --defaults-file=/etc/nexus-mail-admin.cnf <<SQLEOF
INSERT INTO mailbox (username, password, name, maildir, quota, domain, active, created, modified)
VALUES ('$EMAIL', '$HASH', '$LOCAL', '$MAILDIR_PATH', 1024, '$DOMAIN', 1, NOW(), NOW());
SQLEOF

# Also create matching alias (required by iRedMail)
mysql --defaults-file=/etc/nexus-mail-admin.cnf <<SQLEOF
INSERT IGNORE INTO alias (address, goto, domain, active)
VALUES ('$EMAIL', '$EMAIL', '$DOMAIN', 1);
SQLEOF

# Create maildir on disk
FULL_MAILDIR="/var/vmail/vmail1/$MAILDIR_PATH/Maildir"
mkdir -p "$FULL_MAILDIR"/{cur,new,tmp}
chown -R vmail:vmail "/var/vmail/vmail1/$DOMAIN/$FIRST"

echo "{\"ok\":true,\"email\":\"$EMAIL\",\"action\":\"created\",\"maildir\":\"$MAILDIR_PATH\"}"
echo "$(date -Iseconds) create_mailbox OK email=$EMAIL" >> "$LOG"
"""

stdin, stdout, stderr = ssh.exec_command(
    "cat > /opt/nexus-mail-admin/create_mailbox && chmod 755 /opt/nexus-mail-admin/create_mailbox"
)
stdin.write(script)
stdin.channel.shutdown_write()
stdout.read()

# Test
print("Testing create_mailbox...")
stdin2, stdout2, stderr2 = ssh.exec_command(
    "bash /opt/nexus-mail-admin/create_mailbox nexus-inbox@gsmcall.com TestPass1234"
)
out = stdout2.read().decode().strip()
err = stderr2.read().decode().strip()
code = stdout2.channel.recv_exit_status()
print(f"  stdout: {out}")
if err:
    print(f"  stderr: {err}")
print(f"  exit: {code}")

# Now set the real password from vault for this mailbox
if code == 0:
    import secrets as sec
    import string

    real_pass = "".join(
        sec.choice(string.ascii_letters + string.digits + "!@#%^") for _ in range(24)
    )
    stdin3, stdout3, stderr3 = ssh.exec_command(
        f"bash /opt/nexus-mail-admin/set_password nexus-inbox@gsmcall.com '{real_pass}'"
    )
    print(f"\nset_password: {stdout3.read().decode().strip()}")

    # Update vault with real password
    import httpx

    VAULT_H = {
        "X-Service-ID": "nexus",
        "X-Agent-Key": "nexus-internal-key",
        "Content-Type": "application/json",
    }
    resp = httpx.get(
        "http://localhost:8007/v1/secrets",
        params={"tenant_id": "nexus", "env": "prod"},
        headers=VAULT_H,
    )
    imap_pw = next((s for s in resp.json() if s["alias"] == "email.imap.password"), None)
    if imap_pw:
        r = httpx.post(
            f"http://localhost:8007/v1/secrets/{imap_pw['id']}/rotate",
            json={"new_value": real_pass, "reason": "nexus_inbox_password_set"},
            headers=VAULT_H,
        )
        print(f"Vault password rotated: {r.status_code}")

# Verify via list
stdin4, stdout4, stderr4 = ssh.exec_command("sudo /opt/nexus-mail-admin/list_mailboxes")
import json

data = json.loads(stdout4.read().decode())
inbox = [m for m in data if "nexus-inbox" in m["email"]]
print(f"\nVerification: {inbox}")

ssh.close()
