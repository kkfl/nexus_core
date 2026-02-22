#!/usr/bin/env bash
set -eo pipefail

APP_DIR="/opt/nexus"
COMPOSE_FILE="infra/prod/docker-compose.prod.yml"
ENV_FILE="infra/prod/env/nexus.env"

echo "========================================"
echo "         Nexus Deploy Script            "
echo "========================================"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Environment file $ENV_FILE not found."
  echo "Please copy $ENV_FILE.example, configure it, and retry."
  exit 1
fi

# Load env variables for healthcheck script later
source "$ENV_FILE"

# Determine profiles based on managed overrides
PROFILE_ARGS=""
if [ "${USE_MANAGED_POSTGRES}" != "true" ]; then
  PROFILE_ARGS="$PROFILE_ARGS --profile local_db"
fi
if [ "${USE_MANAGED_S3}" != "true" ]; then
  PROFILE_ARGS="$PROFILE_ARGS --profile local_s3"
fi

echo "1. Pulling latest images/code..."
# git pull origin main (assuming you are in a repo)
cd $APP_DIR

echo "2. Building updated containers..."
docker compose -f $COMPOSE_FILE $PROFILE_ARGS build

echo "3. Starting stack (detached)..."
docker compose -f $COMPOSE_FILE $PROFILE_ARGS up -d

echo "4. Running database migrations..."
if [ "${USE_MANAGED_POSTGRES}" != "true" ]; then
  # Wait for postgres to be ready
  echo "Waiting for PostgreSQL to be ready..."
  sleep 5
fi

docker compose -f $COMPOSE_FILE exec -T nexus-api alembic upgrade head

echo "5. Verifying health (Post-deploy checks)..."
./infra/prod/scripts/healthcheck.sh || {
  echo ""
  echo "⚠️ HEALTHCHECK FAILED!"
  echo "Rollback Steps:"
  echo "  1. View logs: docker compose -f $COMPOSE_FILE logs -f"
  echo "  2. Rollback git: git checkout 'previous-commit-hash'"
  echo "  3. Re-run deploy.sh"
  exit 1
}

# Optional: Restart Caddy if configuration changed (and is running on host)
if systemctl is-active --quiet caddy; then
  echo "Reloading Caddy..."
  sudo cp infra/prod/caddy/Caddyfile /etc/caddy/Caddyfile
  sudo mkdir -p /etc/caddy/snippets
  sudo cp infra/prod/caddy/snippets/* /etc/caddy/snippets/
  sudo systemctl reload caddy
fi

echo "========================================"
echo "    Deployment Successfully Complete!   "
echo "========================================"
