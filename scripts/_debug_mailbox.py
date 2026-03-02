"""Fix create_mailbox SQL — remove local_part column."""

import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("mx.gsmcall.com", port=2007, username="root", password="G$Mcall01", timeout=10)

# Check actual mailbox table schema
stdin, stdout, stderr = ssh.exec_command(
    "mysql --defaults-file=/etc/nexus-mail-admin.cnf -e 'DESCRIBE mailbox;'"
)
print("=== mailbox table schema ===")
print(stdout.read().decode())

ssh.close()
