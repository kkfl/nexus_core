#!/usr/bin/env bash
set -e

echo "========================================"
echo "          Nexus Restore Script          "
echo "========================================"

if [ "${CONFIRM_RESTORE}" != "true" ]; then
    echo "🚨 WARNING: This script will DESTROY existing database data."
    echo "To proceed, you MUST set the environment variable CONFIRM_RESTORE=true"
    echo "Example: CONFIRM_RESTORE=true ./restore.sh s3://mybucket/backups/file.sql.gz"
    exit 1
fi

if [ -z "$1" ]; then
    echo "Usage: CONFIRM_RESTORE=true ./restore.sh <s3_path_or_local_file>"
    echo "Example: ./restore.sh s3://nexus-artifacts/backups/postgres/2026/02/21/dump.sql.gz"
    echo "Example: ./restore.sh /opt/nexus/backups/dump.sql.gz"
    exit 1
fi

SOURCE="$1"
LOCAL_TMP="/tmp/nexus_restore_tmp.sql.gz"
ENV_FILE="/opt/nexus/infra/prod/env/nexus.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing environment file at $ENV_FILE"
  exit 1
fi
source "$ENV_FILE"

echo "1. Fetching backup from ${SOURCE}..."
if [[ "$SOURCE" == s3://* ]]; then
    S3_ENDPOINT=${STORAGE_S3_ENDPOINT:-"http://127.0.0.1:9000"}
    
    docker run --rm \
        -e AWS_ACCESS_KEY_ID="${STORAGE_S3_ACCESS_KEY:-$MINIO_ROOT_USER}" \
        -e AWS_SECRET_ACCESS_KEY="${STORAGE_S3_SECRET_KEY:-$MINIO_ROOT_PASSWORD}" \
        amazon/aws-cli \
        --endpoint-url "${S3_ENDPOINT}" \
        s3 cp "${SOURCE}" - > "${LOCAL_TMP}"
else
    cp "$SOURCE" "${LOCAL_TMP}"
fi

echo "2. Dropping existing connections and database..."
# Terminate existing connections
docker exec nexus-postgres psql -U nexus -d postgres -c "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = 'nexus_core' AND pid <> pg_backend_pid();"
docker exec nexus-postgres psql -U nexus -d postgres -c "DROP DATABASE nexus_core;"
docker exec nexus-postgres psql -U nexus -d postgres -c "CREATE DATABASE nexus_core;"

echo "3. Restoring data..."
gunzip -c "${LOCAL_TMP}" | docker exec -i nexus-postgres psql -U nexus -d nexus_core

rm -f "${LOCAL_TMP}"

echo "========================================"
echo "   Restore Successfully Completed!      "
echo "========================================"
