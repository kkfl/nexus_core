#!/usr/bin/env bash
set -eo pipefail

echo "========================================"
echo "     Nexus Healthcheck                  "
echo "========================================"

URL=${NEXUS_API_URL:-"http://127.0.0.1:8000"}

echo "Checking /healthz API Endpoint..."
API_HEALTH=$(curl -s -f -o /dev/null -w "%{http_code}" "${URL}/healthz" || echo "Fail")

if [ "$API_HEALTH" != "200" ]; then
    echo "ERROR: /healthz endpoint returned $API_HEALTH"
    exit 1
fi

echo "Checking /readyz API Endpoint..."
API_READY=$(curl -s -f -o /dev/null -w "%{http_code}" "${URL}/readyz" || echo "Fail")

if [ "$API_READY" != "200" ]; then
    echo "ERROR: /readyz endpoint returned $API_READY (API is running but dependencies might be down)"
    exit 1
fi

echo "All basic API checks passed."

# Optional: Ping DB Directly if it's the local container
if docker ps | grep -q nexus-postgres; then
    echo "Checking local PostgreSQL container..."
    if ! docker exec nexus-postgres pg_isready -U nexus -d nexus_core >/dev/null; then
        echo "ERROR: PostgreSQL container is not responsive."
        exit 1
    fi
fi

echo "SUCCESS: Nexus Stack is healthy."
