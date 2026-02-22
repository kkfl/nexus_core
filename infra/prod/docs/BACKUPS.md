# Nexus Backup Strategy

Data persistence in Nexus Core V1 relies on Postgres (canonical state, metadata, secrets) and an S3-compatible Blob store (Files, Artifacts).

As long as you are using an External managed Database (like AWS RDS) and S3 bucket, **use the cloud provider's snapshot tooling.**

If you are using the local Postgres/MinIO containers, you MUST use the provided automation.

## 1. Backup Script (`backup.sh`)
The `infra/prod/scripts/backup.sh` script handles:
- Using `pg_dump` on the live container to create a gzip-compressed `.sql.gz` artifact.
- Persisting it locally to `/opt/nexus/backups/postgres/YYYY/MM/DD/`.
- Automatically calling the AWS CLI to upload the backup to the configured `STORAGE_S3_BUCKET`.
- Pruning local backups older than 7 days.

## 2. Automated Daily Backups
To run the script automatically every day at 03:15 AM server time:
```bash
sudo cp infra/prod/systemd/nexus-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nexus-backup.timer
```
You can view the logs for automated backups via:
`sudo journalctl -u nexus-backup.service`

## 3. Restoring from a Backup
The `restore.sh` script forcefully drops the current database and re-imports the SQL dump.

> **⚠️ WARNING:** This operation is highly destructive. It will obliterate the current system state.

To prevent accidental execution, the script requires an explicit environment variable override:

**Restore from Remote S3:**
```bash
CONFIRM_RESTORE=true ./infra/prod/scripts/restore.sh s3://nexus-artifacts/backups/postgres/2026/02/21/nexus_db_1234.sql.gz
```

**Restore from Local File:**
```bash
CONFIRM_RESTORE=true ./infra/prod/scripts/restore.sh /opt/nexus/backups/postgres/2026/02/21/nexus_db_1234.sql.gz
```
