"""
One-time iRedMail server setup via SSH (paramiko).
Creates nexusops user, deploys SSH key, checks port 587, lists mailboxes.
"""

import os
from pathlib import Path

import paramiko

HOST = "mx.gsmcall.com"
PORT = 2007
USER = "root"
PASS = os.environ.get("IREDMAIL_ROOT_PASS", "G$Mcall01")

PUBKEY_PATH = os.path.join(os.environ["USERPROFILE"], ".ssh", "nexus_iredmail.pub")


def run_cmd(ssh, cmd, label=""):
    if label:
        print(f"\n=== {label} ===")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(f"  [stderr] {err}")
    return out


def main():
    pubkey = Path(PUBKEY_PATH).read_text().strip()
    print(f"Public key: {pubkey[:50]}...")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"\nConnecting to {HOST}:{PORT} as {USER}...")
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=10)
    print("Connected!")

    # Step 1: Create nexusops user
    run_cmd(
        ssh,
        """
        if id nexusops >/dev/null 2>&1; then
            echo 'User nexusops already exists'
        else
            adduser --disabled-password --gecos '' nexusops
            echo 'User nexusops CREATED'
        fi
    """,
        "Step 1: Create nexusops user",
    )

    # Step 2: Deploy SSH key
    run_cmd(
        ssh,
        f"""
        mkdir -p /home/nexusops/.ssh
        chmod 700 /home/nexusops/.ssh
        echo '{pubkey}' > /home/nexusops/.ssh/authorized_keys
        chmod 600 /home/nexusops/.ssh/authorized_keys
        chown -R nexusops:nexusops /home/nexusops/.ssh
        passwd -l nexusops 2>/dev/null || true
        echo 'SSH key deployed for nexusops'
    """,
        "Step 2: Deploy SSH key",
    )

    # Step 3: Lock down SSH
    run_cmd(
        ssh,
        """
        if grep -q 'Match User nexusops' /etc/ssh/sshd_config; then
            echo 'SSH match block already exists'
        else
            printf '\\nMatch User nexusops\\n  PasswordAuthentication no\\n  KbdInteractiveAuthentication no\\n' >> /etc/ssh/sshd_config
            systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true
            echo 'SSH config updated and restarted'
        fi
    """,
        "Step 3: Lock down SSH for nexusops",
    )

    # Step 4: Check port 587
    run_cmd(
        ssh,
        "ss -lntp | grep ':587' || echo 'WARNING: Port 587 NOT listening'",
        "Step 4: Check port 587",
    )

    # Step 5: Check mail system
    run_cmd(
        ssh,
        "postconf -h myhostname 2>/dev/null || echo 'postfix not found'",
        "Step 5: Mail system hostname",
    )

    # Step 6: List existing mailboxes
    run_cmd(
        ssh,
        """
        if command -v mysql >/dev/null 2>&1; then
            echo 'Backend: MySQL/MariaDB'
            mysql -u root vmail -e "SELECT username, domain, active FROM mailbox WHERE domain='gsmcall.com';" 2>/dev/null || echo 'Could not query mailbox table'
        else
            echo 'MySQL not found — checking for OpenLDAP or PostgreSQL backend'
        fi
    """,
        "Step 6: Existing mailboxes",
    )

    # Step 7: Check if alerts@gsmcall.com already exists
    result = run_cmd(
        ssh,
        """
        mysql -u root vmail -e "SELECT username FROM mailbox WHERE username='alerts@gsmcall.com';" 2>/dev/null | tail -1
    """,
        "Step 7: Check alerts@gsmcall.com",
    )

    if "alerts@gsmcall.com" in result:
        print("  alerts@gsmcall.com ALREADY EXISTS")
    else:
        print("  alerts@gsmcall.com does not exist yet — will need to create it")

    ssh.close()
    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
