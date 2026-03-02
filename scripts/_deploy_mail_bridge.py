"""
Deploy the SSH command bridge scripts to mx.gsmcall.com.

This script:
1. Detects DB connection info from dovecot config
2. Detects password scheme
3. Creates a dedicated DB user
4. Deploys admin scripts to /opt/nexus-mail-admin/
5. Configures sudoers for nexusops
"""

import json

import paramiko

HOST = "mx.gsmcall.com"
PORT = 2007
USER = "root"
PASS = "G$Mcall01"


def ssh_connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=10)
    return ssh


def run(ssh, cmd, label=""):
    if label:
        print(f"\n=== {label} ===")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err and "Warning" not in err:
        print(f"  [stderr] {err}")
    return out


def main():
    ssh = ssh_connect()
    print("Connected to mx.gsmcall.com")

    # Step 1: Detect DB connection
    run(
        ssh,
        r"""
        grep -E '^connect\s*=' /etc/dovecot/dovecot-sql.conf.ext | head -1
    """,
        "Step 1: DB Connection Info",
    )

    # Step 2: Detect password scheme
    run(
        ssh,
        """
        doveconf -n 2>/dev/null | grep default_pass_scheme || echo 'default_pass_scheme not found'
    """,
        "Step 2: Password Scheme",
    )

    # Step 3: Get existing DB details for script config
    run(
        ssh,
        """
        grep -E 'driver|connect' /etc/dovecot/dovecot-sql.conf.ext | head -5
    """,
        "Step 3: Full DB Config",
    )

    # Step 4: Create /etc/nexus-mail-admin.cnf with DB creds (parse from dovecot config)
    run(
        ssh,
        r"""
        # Parse connection string from dovecot
        CONN=$(grep -E '^connect\s*=' /etc/dovecot/dovecot-sql.conf.ext | sed 's/^connect\s*=\s*//')
        
        # Extract individual fields
        DB_HOST=$(echo "$CONN" | grep -oP 'host=\K[^ ]+' || echo 'localhost')
        DB_PORT=$(echo "$CONN" | grep -oP 'port=\K[^ ]+' || echo '3306')
        DB_NAME=$(echo "$CONN" | grep -oP 'dbname=\K[^ ]+' || echo 'vmail')
        DB_USER=$(echo "$CONN" | grep -oP 'user=\K[^ ]+' || echo 'vmail')
        DB_PASS=$(echo "$CONN" | grep -oP 'password=\K[^ ]+' || echo '')

        # Create dedicated DB user for admin scripts
        mysql -u root -e "
            CREATE USER IF NOT EXISTS 'nexus_mail_admin'@'localhost' IDENTIFIED BY 'NxMailAdm!2026secure';
            GRANT SELECT, INSERT, UPDATE ON vmail.mailbox TO 'nexus_mail_admin'@'localhost';
            GRANT SELECT, INSERT, UPDATE, DELETE ON vmail.alias TO 'nexus_mail_admin'@'localhost';
            GRANT SELECT ON vmail.domain TO 'nexus_mail_admin'@'localhost';
            FLUSH PRIVILEGES;
        " 2>/dev/null && echo 'DB user nexus_mail_admin created/updated' || echo 'DB user creation failed'

        # Write cnf file
        cat > /etc/nexus-mail-admin.cnf <<'CNFEOF'
[client]
host = localhost
port = 3306
database = vmail
user = nexus_mail_admin
password = NxMailAdm!2026secure
CNFEOF
        chmod 600 /etc/nexus-mail-admin.cnf
        chown root:root /etc/nexus-mail-admin.cnf
        echo 'Created /etc/nexus-mail-admin.cnf (root:root 600)'
    """,
        "Step 4: Create DB User + Config File",
    )

    # Step 5: Deploy admin scripts
    run(
        ssh,
        "mkdir -p /opt/nexus-mail-admin && chmod 755 /opt/nexus-mail-admin",
        "Step 5: Create script directory",
    )

    # --- list_mailboxes ---
    run(
        ssh,
        r"""cat > /opt/nexus-mail-admin/list_mailboxes <<'SCRIPTEOF'
#!/bin/bash
# List all mailboxes — outputs JSON array
set -euo pipefail

LOG="/var/log/nexus-mail-admin.log"
echo "$(date -Iseconds) list_mailboxes invoked by $(whoami)" >> "$LOG"

RESULT=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e "
    SELECT JSON_ARRAYAGG(
        JSON_OBJECT(
            'email', username,
            'domain', domain,
            'active', CAST(active AS UNSIGNED),
            'quota', CAST(quota AS UNSIGNED),
            'created', created
        )
    ) FROM mailbox ORDER BY domain, username;
" 2>/dev/null)

if [ -z "$RESULT" ] || [ "$RESULT" = "null" ]; then
    echo '[]'
else
    echo "$RESULT"
fi
SCRIPTEOF
chmod 755 /opt/nexus-mail-admin/list_mailboxes
echo 'Deployed list_mailboxes'""",
    )

    # --- create_mailbox ---
    run(
        ssh,
        r"""cat > /opt/nexus-mail-admin/create_mailbox <<'SCRIPTEOF'
#!/bin/bash
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
DOMAIN_EXISTS=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e "
    SELECT COUNT(*) FROM domain WHERE domain='$DOMAIN';
" 2>/dev/null)

if [ "$DOMAIN_EXISTS" = "0" ]; then
    echo "{\"ok\":false,\"error\":\"domain '$DOMAIN' not found in mail system\"}"
    echo "$(date -Iseconds) create_mailbox FAIL domain_not_found email=$EMAIL" >> "$LOG"
    exit 1
fi

# Check if already exists
EXISTS=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e "
    SELECT COUNT(*) FROM mailbox WHERE username='$EMAIL';
" 2>/dev/null)

if [ "$EXISTS" != "0" ]; then
    echo "{\"ok\":true,\"email\":\"$EMAIL\",\"action\":\"already_exists\"}"
    echo "$(date -Iseconds) create_mailbox SKIP already_exists email=$EMAIL" >> "$LOG"
    exit 0
fi

# Generate password hash
SCHEME=$(doveconf -n 2>/dev/null | grep -oP 'default_pass_scheme\s*=\s*\K\S+' || echo 'SSHA512')
HASH=$(doveadm pw -s "$SCHEME" -p "$PASS")

# Determine maildir path
MAILDIR_BASE="$DOMAIN/$LOCAL-$(date +%Y%m%d%H%M%S)/"
STORAGE_BASE="/var/vmail/vmail1"

# Insert mailbox
mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
    INSERT INTO mailbox (username, password, name, maildir, quota, domain, active, local_part, created)
    VALUES ('$EMAIL', '$HASH', '$LOCAL', '$MAILDIR_BASE', 1024, '$DOMAIN', 1, '$LOCAL', NOW());
" 2>/dev/null

# Also create matching alias (required by iRedMail)
mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
    INSERT IGNORE INTO alias (address, goto, domain, active)
    VALUES ('$EMAIL', '$EMAIL', '$DOMAIN', 1);
" 2>/dev/null

# Create maildir
FULL_MAILDIR="$STORAGE_BASE/$MAILDIR_BASE"
mkdir -p "$FULL_MAILDIR"/{cur,new,tmp}
chown -R vmail:vmail "$FULL_MAILDIR"

echo "{\"ok\":true,\"email\":\"$EMAIL\",\"action\":\"created\",\"maildir\":\"$MAILDIR_BASE\"}"
echo "$(date -Iseconds) create_mailbox OK email=$EMAIL" >> "$LOG"
SCRIPTEOF
chmod 755 /opt/nexus-mail-admin/create_mailbox
echo 'Deployed create_mailbox'""",
    )

    # --- set_password ---
    run(
        ssh,
        r"""cat > /opt/nexus-mail-admin/set_password <<'SCRIPTEOF'
#!/bin/bash
# Reset mailbox password
# Usage: set_password <email> <new_password>
set -euo pipefail

LOG="/var/log/nexus-mail-admin.log"
EMAIL="${1:-}"
PASS="${2:-}"

if [ -z "$EMAIL" ] || [ -z "$PASS" ]; then
    echo '{"ok":false,"error":"usage: set_password <email> <password>"}'
    exit 1
fi

EXISTS=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e "
    SELECT COUNT(*) FROM mailbox WHERE username='$EMAIL';
" 2>/dev/null)

if [ "$EXISTS" = "0" ]; then
    echo "{\"ok\":false,\"error\":\"mailbox '$EMAIL' not found\"}"
    echo "$(date -Iseconds) set_password FAIL not_found email=$EMAIL" >> "$LOG"
    exit 1
fi

SCHEME=$(doveconf -n 2>/dev/null | grep -oP 'default_pass_scheme\s*=\s*\K\S+' || echo 'SSHA512')
HASH=$(doveadm pw -s "$SCHEME" -p "$PASS")

mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
    UPDATE mailbox SET password='$HASH' WHERE username='$EMAIL';
" 2>/dev/null

echo "{\"ok\":true,\"email\":\"$EMAIL\",\"action\":\"password_updated\"}"
echo "$(date -Iseconds) set_password OK email=$EMAIL" >> "$LOG"
SCRIPTEOF
chmod 755 /opt/nexus-mail-admin/set_password
echo 'Deployed set_password'""",
    )

    # --- disable_mailbox ---
    run(
        ssh,
        r"""cat > /opt/nexus-mail-admin/disable_mailbox <<'SCRIPTEOF'
#!/bin/bash
# Disable a mailbox (set active=0)
# Usage: disable_mailbox <email>
set -euo pipefail

LOG="/var/log/nexus-mail-admin.log"
EMAIL="${1:-}"

if [ -z "$EMAIL" ]; then
    echo '{"ok":false,"error":"usage: disable_mailbox <email>"}'
    exit 1
fi

ACTIVE=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e "
    SELECT active FROM mailbox WHERE username='$EMAIL';
" 2>/dev/null)

if [ -z "$ACTIVE" ]; then
    echo "{\"ok\":false,\"error\":\"mailbox '$EMAIL' not found\"}"
    echo "$(date -Iseconds) disable_mailbox FAIL not_found email=$EMAIL" >> "$LOG"
    exit 1
fi

if [ "$ACTIVE" = "0" ]; then
    echo "{\"ok\":true,\"email\":\"$EMAIL\",\"action\":\"already_disabled\"}"
    echo "$(date -Iseconds) disable_mailbox SKIP already_disabled email=$EMAIL" >> "$LOG"
    exit 0
fi

mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
    UPDATE mailbox SET active=0 WHERE username='$EMAIL';
" 2>/dev/null

echo "{\"ok\":true,\"email\":\"$EMAIL\",\"action\":\"disabled\"}"
echo "$(date -Iseconds) disable_mailbox OK email=$EMAIL" >> "$LOG"
SCRIPTEOF
chmod 755 /opt/nexus-mail-admin/disable_mailbox
echo 'Deployed disable_mailbox'""",
    )

    # --- add_alias ---
    run(
        ssh,
        r"""cat > /opt/nexus-mail-admin/add_alias <<'SCRIPTEOF'
#!/bin/bash
# Add a mail alias
# Usage: add_alias <alias_address> <destination_address>
set -euo pipefail

LOG="/var/log/nexus-mail-admin.log"
ALIAS="${1:-}"
DEST="${2:-}"

if [ -z "$ALIAS" ] || [ -z "$DEST" ]; then
    echo '{"ok":false,"error":"usage: add_alias <alias> <destination>"}'
    exit 1
fi

DOMAIN=$(echo "$ALIAS" | cut -d@ -f2)

# Check domain exists
DOMAIN_EXISTS=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e "
    SELECT COUNT(*) FROM domain WHERE domain='$DOMAIN';
" 2>/dev/null)

if [ "$DOMAIN_EXISTS" = "0" ]; then
    echo "{\"ok\":false,\"error\":\"domain '$DOMAIN' not found\"}"
    echo "$(date -Iseconds) add_alias FAIL domain_not_found alias=$ALIAS dest=$DEST" >> "$LOG"
    exit 1
fi

# Check if alias already exists with same destination
EXISTS=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e "
    SELECT COUNT(*) FROM alias WHERE address='$ALIAS' AND goto='$DEST';
" 2>/dev/null)

if [ "$EXISTS" != "0" ]; then
    echo "{\"ok\":true,\"alias\":\"$ALIAS\",\"destination\":\"$DEST\",\"action\":\"already_exists\"}"
    echo "$(date -Iseconds) add_alias SKIP already_exists alias=$ALIAS dest=$DEST" >> "$LOG"
    exit 0
fi

mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
    INSERT INTO alias (address, goto, domain, active)
    VALUES ('$ALIAS', '$DEST', '$DOMAIN', 1)
    ON DUPLICATE KEY UPDATE goto=CONCAT(goto, ',', '$DEST');
" 2>/dev/null

echo "{\"ok\":true,\"alias\":\"$ALIAS\",\"destination\":\"$DEST\",\"action\":\"created\"}"
echo "$(date -Iseconds) add_alias OK alias=$ALIAS dest=$DEST" >> "$LOG"
SCRIPTEOF
chmod 755 /opt/nexus-mail-admin/add_alias
echo 'Deployed add_alias'""",
    )

    # Step 6: Configure sudoers
    run(
        ssh,
        r"""
        cat > /etc/sudoers.d/nexusops-mail-admin <<'SUDOEOF'
# Allow nexusops to run only nexus-mail-admin scripts, no password
nexusops ALL=(root) NOPASSWD: /opt/nexus-mail-admin/list_mailboxes
nexusops ALL=(root) NOPASSWD: /opt/nexus-mail-admin/create_mailbox
nexusops ALL=(root) NOPASSWD: /opt/nexus-mail-admin/set_password
nexusops ALL=(root) NOPASSWD: /opt/nexus-mail-admin/disable_mailbox
nexusops ALL=(root) NOPASSWD: /opt/nexus-mail-admin/add_alias
SUDOEOF
        chmod 440 /etc/sudoers.d/nexusops-mail-admin
        visudo -cf /etc/sudoers.d/nexusops-mail-admin && echo 'Sudoers valid' || echo 'Sudoers INVALID'
    """,
        "Step 6: Configure sudoers",
    )

    # Step 7: Create log file
    run(
        ssh,
        """
        touch /var/log/nexus-mail-admin.log
        chmod 644 /var/log/nexus-mail-admin.log
        echo 'Log file ready'
    """,
        "Step 7: Create log file",
    )

    # Step 8: Verify scripts via nexusops (as non-root, via sudo)
    ssh.close()
    print("\n=== Step 8: Verify via nexusops SSH ===")

    # Connect as nexusops with key
    import os

    ssh2 = paramiko.SSHClient()
    ssh2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key_path = os.path.join(os.environ["USERPROFILE"], ".ssh", "nexus_iredmail")
    pkey = paramiko.Ed25519Key.from_private_key_file(key_path)
    ssh2.connect(HOST, port=PORT, username="nexusops", pkey=pkey, timeout=10)
    print("Connected as nexusops (SSH key)")

    out = run(ssh2, "sudo /opt/nexus-mail-admin/list_mailboxes", "list_mailboxes (via nexusops)")
    try:
        data = json.loads(out)
        print(f"  Parsed {len(data)} mailbox(es)")
        for m in data[:5]:
            print(f"    {m['email']} active={m['active']}")
    except Exception as e:
        print(f"  JSON parse error: {e}")

    ssh2.close()
    print("\n=== DEPLOYMENT COMPLETE ===")


if __name__ == "__main__":
    main()
