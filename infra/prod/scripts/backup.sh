#!/usr/bin/env bash
set -eo pipefail

echo "========================================"
echo "          Nexus Backup Script           "
echo "========================================"

# Default backup path
BACKUP_DIR="/opt/nexus/backups/postgres"
DATE=$(date +"%Y/%m/%d")
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILE_NAME="nexus_db_${TIMESTAMP}.sql.gz"
LOCAL_PATH="${BACKUP_DIR}/${DATE}/${FILE_NAME}"

mkdir -p "${BACKUP_DIR}/${DATE}"

ENV_FILE="/opt/nexus/infra/prod/env/nexus.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing environment file at $ENV_FILE"
  exit 1
fi
source "$ENV_FILE"

echo "1. Dumping PostgreSQL database..."
docker exec nexus-postgres pg_dump -U nexus nexus_core | gzip > "${LOCAL_PATH}"

echo "2. Backup created at: ${LOCAL_PATH}"

# S3 Upload Setup
S3_ENDPOINT=${STORAGE_S3_ENDPOINT:-"http://127.0.0.1:9000"}
S3_BUCKET=${STORAGE_S3_BUCKET:-"nexus-artifacts"}
S3_KEY="backups/postgres/${DATE}/${FILE_NAME}"

# We use docker to run AWS CLI so we don't need it installed on the host
# Pass MINIO credentials as AWS credentials
echo "3. Uploading to S3..."
docker run --rm \
  -e AWS_ACCESS_KEY_ID="${STORAGE_S3_ACCESS_KEY:-$MINIO_ROOT_USER}" \
  -e AWS_SECRET_ACCESS_KEY="${STORAGE_S3_SECRET_KEY:-$MINIO_ROOT_PASSWORD}" \
  amazon/aws-cli \
  --endpoint-url "${S3_ENDPOINT}" \
  s3 cp - "s3://${S3_BUCKET}/${S3_KEY}" < "${LOCAL_PATH}"

echo "4. Upload Complete: s3://${S3_BUCKET}/${S3_KEY}"

# Basic retention Policy for Local Backups (Keep 7 days)
echo "5. Cleaning up old local backups..."
find "${BACKUP_DIR}" -type f -mtime +7 -name '*.sql.gz' -exec rm {} \;

echo "Backup successful!"
