#!/bin/bash
set -e

echo '=== Step 1: Create nexusops user ==='
if id nexusops >/dev/null 2>&1; then
  echo 'User nexusops already exists'
else
  adduser --disabled-password --gecos '' nexusops
  echo 'User nexusops created'
fi

echo '=== Step 2: Setup SSH key ==='
mkdir -p /home/nexusops/.ssh
chmod 700 /home/nexusops/.ssh
echo 'PUBKEY_PLACEHOLDER' > /home/nexusops/.ssh/authorized_keys
chmod 600 /home/nexusops/.ssh/authorized_keys
chown -R nexusops:nexusops /home/nexusops/.ssh
passwd -l nexusops 2>/dev/null || true
echo 'SSH key deployed'

echo '=== Step 3: Lock down SSH for nexusops ==='
if grep -q 'Match User nexusops' /etc/ssh/sshd_config; then
  echo 'SSH match block already exists'
else
  printf '\nMatch User nexusops\n  PasswordAuthentication no\n  KbdInteractiveAuthentication no\n' >> /etc/ssh/sshd_config
  systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true
  echo 'SSH config updated and restarted'
fi

echo '=== Step 4: Check port 587 ==='
ss -lntp | grep ':587' || echo 'WARNING: Port 587 not listening'

echo '=== Step 5: Check mail system ==='
postconf -h myhostname 2>/dev/null || echo 'postfix not found'

echo '=== Step 6: Check existing mailboxes ==='
if command -v mysql >/dev/null 2>&1; then
  echo 'Backend: MySQL/MariaDB'
  mysql -u root vmail -e "SELECT username FROM mailbox WHERE domain='gsmcall.com' LIMIT 20;" 2>/dev/null || echo 'Could not query mailbox table'
fi

echo '=== DONE ==='
