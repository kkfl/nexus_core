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
        # Create forwardings table if missing (required by Postfix virtual_alias_maps)
        mysql -u root vmail -e "
            CREATE TABLE IF NOT EXISTS forwardings (
                id BIGINT(20) UNSIGNED AUTO_INCREMENT,
                address VARCHAR(255) NOT NULL DEFAULT '',
                forwarding VARCHAR(255) NOT NULL DEFAULT '',
                domain VARCHAR(255) NOT NULL DEFAULT '',
                dest_domain VARCHAR(255) NOT NULL DEFAULT '',
                is_forwarding TINYINT(1) NOT NULL DEFAULT 0,
                is_alias TINYINT(1) NOT NULL DEFAULT 0,
                is_maillist TINYINT(1) NOT NULL DEFAULT 0,
                active TINYINT(1) NOT NULL DEFAULT 1,
                PRIMARY KEY (id),
                UNIQUE KEY (address, forwarding),
                INDEX (domain),
                INDEX (dest_domain),
                INDEX (is_forwarding)
            ) ENGINE=InnoDB;
        " 2>/dev/null && echo 'forwardings table ensured'

        # Populate forwardings with self-delivery entries for existing mailboxes
        mysql -u root vmail -e "
            INSERT IGNORE INTO forwardings (address, forwarding, domain, dest_domain, is_forwarding, active)
            SELECT username, username, domain, domain, 0, 1 FROM mailbox WHERE active=1;
        " 2>/dev/null && echo 'forwardings populated from existing mailboxes'

        # Create dedicated DB user for admin scripts
        mysql -u root -e "
            CREATE USER IF NOT EXISTS 'nexus_mail_admin'@'localhost' IDENTIFIED BY 'NxMailAdm!2026secure';
            GRANT SELECT, INSERT, UPDATE ON vmail.mailbox TO 'nexus_mail_admin'@'localhost';
            GRANT SELECT, INSERT, UPDATE, DELETE ON vmail.alias TO 'nexus_mail_admin'@'localhost';
            GRANT SELECT, INSERT, UPDATE ON vmail.domain TO 'nexus_mail_admin'@'localhost';
            GRANT SELECT, INSERT, UPDATE, DELETE ON vmail.forwardings TO 'nexus_mail_admin'@'localhost';
            FLUSH PRIVILEGES;
        " 2>/dev/null && echo 'DB user nexus_mail_admin created/updated' || echo 'DB user creation failed'

        # Ensure vmail user (used by Postfix proxy maps) has SELECT on all vmail tables
        mysql -u root -e "
            GRANT SELECT ON vmail.* TO 'vmail'@'127.0.0.1';
            FLUSH PRIVILEGES;
        " 2>/dev/null && echo 'vmail grants ensured'

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
# Create a new mailbox (auto-creates domain if needed)
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

# Auto-create domain if it doesn't exist
DOMAIN_EXISTS=$(mysql --defaults-file=/etc/nexus-mail-admin.cnf -N -e "
    SELECT COUNT(*) FROM domain WHERE domain='$DOMAIN';
" 2>/dev/null)

if [ "$DOMAIN_EXISTS" = "0" ]; then
    mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
        INSERT INTO domain (domain, transport, active, created)
        VALUES ('$DOMAIN', 'dovecot', 1, NOW());
    " 2>/dev/null && echo "$(date -Iseconds) create_mailbox auto-created domain=$DOMAIN" >> "$LOG"
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

# Determine maildir path (no trailing slash to avoid double //)
MAILDIR_BASE="$DOMAIN/$LOCAL-$(date +%Y%m%d%H%M%S)"
STORAGE_BASE="/var/vmail/vmail1"

# Insert mailbox
mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
    INSERT INTO mailbox (username, password, name, maildir, quota, domain, active, local_part, created)
    VALUES ('$EMAIL', '$HASH', '$LOCAL', '$MAILDIR_BASE', 1024, '$DOMAIN', 1, '$LOCAL', NOW());
" 2>/dev/null

# Create self-delivery forwarding entry (required by Postfix virtual_alias_maps)
mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
    INSERT IGNORE INTO forwardings (address, forwarding, domain, dest_domain, is_forwarding, active)
    VALUES ('$EMAIL', '$EMAIL', '$DOMAIN', '$DOMAIN', 0, 1);
" 2>/dev/null

# Also create matching alias (required by iRedMail)
mysql --defaults-file=/etc/nexus-mail-admin.cnf -e "
    INSERT IGNORE INTO alias (address, goto, domain, active)
    VALUES ('$EMAIL', '$EMAIL', '$DOMAIN', 1);
" 2>/dev/null

# Create maildir
FULL_MAILDIR="$STORAGE_BASE/$MAILDIR_BASE/Maildir"
mkdir -p "$FULL_MAILDIR"/{cur,new,tmp}
chown -R vmail:vmail "$STORAGE_BASE/$MAILDIR_BASE"

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

    # --- batch_mailbox_stats ---
    run(
        ssh,
        r"""cat > /opt/nexus-mail-admin/batch_mailbox_stats <<'SCRIPTEOF'
#!/bin/bash
# /opt/nexus-mail-admin/batch_mailbox_stats
# Collect quota, unread, total, last-received for ALL mailboxes in one shot.
# Output: JSON array of stat objects.
# Must run as root (via sudo by nexusops).
#
# Usage: sudo /opt/nexus-mail-admin/batch_mailbox_stats [domain_filter]

set -euo pipefail

LOGFILE="/var/log/nexus-mail-admin.log"
START=$(date +%s)
DOMAIN_FILTER="${1:-}"

log() { echo "$(date -Is) batch_mailbox_stats: $*" >> "$LOGFILE"; }
log "started domain_filter='${DOMAIN_FILTER}'"

# Get all users (one per line)
if [ -n "$DOMAIN_FILTER" ]; then
    USERS=$(doveadm user "*@${DOMAIN_FILTER}" 2>/dev/null || true)
else
    USERS=$(doveadm user '*' 2>/dev/null || true)
fi

if [ -z "$USERS" ]; then
    echo "[]"
    log "no users found"
    exit 0
fi

COLLECTED_AT=$(date -Is)
FIRST=true
echo "["

while IFS= read -r USER; do
    [ -z "$USER" ] && continue

    DOMAIN="${USER#*@}"

    # Quota: doveadm quota get -u <user>
    QUOTA_MB=0
    USED_KB=0
    QUOTA_OUT=$(doveadm quota get -u "$USER" 2>/dev/null || true)
    if [ -n "$QUOTA_OUT" ]; then
        STORAGE_LINE=$(echo "$QUOTA_OUT" | grep -i "STORAGE" | head -1 || true)
        if [ -n "$STORAGE_LINE" ]; then
            USED_KB=$(echo "$STORAGE_LINE" | awk '{for(i=1;i<=NF;i++){if($i=="STORAGE"){print $(i+1);exit}}}')
            LIMIT_KB=$(echo "$STORAGE_LINE" | awk '{for(i=1;i<=NF;i++){if($i=="STORAGE"){print $(i+2);exit}}}')
            USED_KB=${USED_KB:-0}
            LIMIT_KB=${LIMIT_KB:-0}
            if [ "$LIMIT_KB" != "-" ] && [ "$LIMIT_KB" != "0" ] 2>/dev/null; then
                QUOTA_MB=$(( LIMIT_KB / 1024 ))
            fi
        fi
    fi

    # Mailbox status: messages + unseen in INBOX
    # NOTE: fields MUST be quoted together as a single argument
    MESSAGES=0
    UNSEEN=0
    STATUS_OUT=$(doveadm mailbox status -u "$USER" "messages unseen" INBOX 2>/dev/null || true)
    if [ -n "$STATUS_OUT" ]; then
        MESSAGES=$(echo "$STATUS_OUT" | grep -oP 'messages=\K[0-9]+' || echo 0)
        UNSEEN=$(echo "$STATUS_OUT" | grep -oP 'unseen=\K[0-9]+' || echo 0)
    fi

    # Calculate derived values
    USED_KB=${USED_KB:-0}
    if ! [[ "$USED_KB" =~ ^[0-9]+$ ]]; then USED_KB=0; fi
    USED_MB=$(awk "BEGIN{printf \"%.1f\", $USED_KB/1024}")
    if [ "$QUOTA_MB" -gt 0 ] 2>/dev/null; then
        USED_PCT=$(awk "BEGIN{printf \"%.1f\", $USED_KB/1024/$QUOTA_MB*100}")
        FREE_MB=$(awk "BEGIN{v=$QUOTA_MB-$USED_KB/1024; if(v<0)v=0; printf \"%.1f\",v}")
        FREE_PCT=$(awk "BEGIN{printf \"%.1f\", 100-$USED_KB/1024/$QUOTA_MB*100}")
    else
        USED_PCT="0.0"
        FREE_MB="0.0"
        FREE_PCT="100.0"
    fi

    # Last received: best-effort from most recent INBOX message
    LAST_RECEIVED="null"
    LAST_OUT=$(doveadm fetch -u "$USER" "date.received" mailbox INBOX 2>/dev/null | tail -1 || true)
    if [ -n "$LAST_OUT" ] && echo "$LAST_OUT" | grep -q "date.received"; then
        LAST_VAL=$(echo "$LAST_OUT" | sed 's/date.received: //')
        LAST_RECEIVED="\"${LAST_VAL}\""
    fi

    # Output JSON object
    if [ "$FIRST" = true ]; then
        FIRST=false
    else
        echo ","
    fi
    cat <<EOF
  {
    "email": "$USER",
    "domain": "$DOMAIN",
    "quota_mb": $QUOTA_MB,
    "used_mb": $USED_MB,
    "used_pct": $USED_PCT,
    "free_mb": $FREE_MB,
    "free_pct": $FREE_PCT,
    "unread_count": $UNSEEN,
    "total_count": $MESSAGES,
    "last_received_at": $LAST_RECEIVED,
    "collected_at": "$COLLECTED_AT"
  }
EOF

done <<< "$USERS"

echo ""
echo "]"

ELAPSED=$(( $(date +%s) - START ))
log "done users=$(echo "$USERS" | wc -l) elapsed=${ELAPSED}s"
SCRIPTEOF
chmod 755 /opt/nexus-mail-admin/batch_mailbox_stats
echo 'Deployed batch_mailbox_stats'""",
    )

    # Step 6: Fix Postfix sender restrictions
    run(
        ssh,
        r"""
        # Fix invalid restriction name and disable unlisted sender rejection
        # (needed when domains like gsmcall.com exist on both O365 and iRedMail)
        postconf -e 'smtpd_sender_restrictions = permit_mynetworks, permit_sasl_authenticated, reject_non_fqdn_sender, reject_unknown_sender_domain'
        postconf -e 'smtpd_reject_unlisted_sender = no'
        systemctl restart postfix && echo 'Postfix config updated and restarted'
    """,
        "Step 6: Fix Postfix sender restrictions",
    )

    # Step 7: Configure sudoers
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
nexusops ALL=(root) NOPASSWD: /opt/nexus-mail-admin/batch_mailbox_stats
SUDOEOF
        chmod 440 /etc/sudoers.d/nexusops-mail-admin
        visudo -cf /etc/sudoers.d/nexusops-mail-admin && echo 'Sudoers valid' || echo 'Sudoers INVALID'
    """,
        "Step 7: Configure sudoers",
    )

    # Step 8: Create log file
    run(
        ssh,
        """
        touch /var/log/nexus-mail-admin.log
        chmod 644 /var/log/nexus-mail-admin.log
        echo 'Log file ready'
    """,
        "Step 8: Create log file",
    )

    # Step 9: Verify scripts via nexusops (as non-root, via sudo)
    ssh.close()
    print("\n=== Step 9: Verify via nexusops SSH ===")

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
