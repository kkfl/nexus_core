# Nexus Core: Go-Live Checklist & Operations Runbook

## 1. Pre-Flight Checklist

Before scaling traffic to the V1 stack, ensure the following constraints:

- [ ] **Infrastructure & Proxies**: 
      Deploy Caddy or a strictly-configured Nginx layer in front of `nexus-api` and `nexus-portal`. Ensure raw HTTP is blocked and TLS is enforced.
- [ ] **Master Key Securely Bootstrapped**:
      Ensure `NEXUS_MASTER_KEY` is a 32-byte Base64-encoded string, securely generated, and NOT committed to version control. Keep a cold backup of this key. If lost, all encrypted credentials in the vault are permanently unrecoverable.
- [ ] **Admin Credentials Rotated**:
      Run the bootstrap script but immediately log in to rotate the default Admin password, or provide securely pre-hashed environment overrides for the bootstrap user.
- [ ] **OpenAPI Docs Disabled**:
      Set `ENABLE_DOCS=false` in the production `.env` to disable `/docs` and `/redoc` interfaces and silence the open schema endpoints.
- [ ] **CORS Locked Down**:
      Set `CORS_ORIGINS` to the exact precise domains expected (e.g., `https://portal.acme.com`).
- [ ] **Feature Flags Secured**:
      Double check `ENABLE_STORAGE_WRITES=false` and `ENABLE_DELETES=false` unless explicitly required by your orchestration tasks in V1.
- [ ] **Database Backups Configuration**: 
      Verify pg_dump runs regularly and is shipped offsite.

## 2. Go-Live Execution Steps

### Deploy Stack
```bash
cp infra/prod/.env.production .env
docker compose -f docker-compose.prod.yml up --build -d
```

### Apply Schema Migrations
```bash
docker compose exec nexus-api alembic upgrade head
```

### Verify Core Health
Check standard endpoints and ensure status code 200:
- `curl -s https://api.yourdomain.com/healthz`
- `curl -s https://api.yourdomain.com/readyz`
- `curl -s https://api.yourdomain.com/metrics`

### Run Release Gate Smoke Tests
Use the golden path smoke tests against the isolated production environment (with MOCK mode safely engaged for agents if applicable initially):
```bash
./tools/golden_paths/run_smoke.sh
```

### Verify Portal
Log into `https://portal.yourdomain.com` with your pre-configured Admin credentials. Ensure the dashboard loads without frontend API errors.

## 3. Rollback Plan

If V1 fails severely and requires immediate rollback:
1. Revert Git pointers to the previous stable schema and tag.
2. If DB schema bumped: You must restore the database via your external backups (e.g., pgBackRest) or run `alembic downgrade [revision_id]` if strictly backward compatible.
3. Bring up the old docker tags: `docker compose up -d` against the restored `.env`.

## 4. Post-Go-Live Monitoring Guidelines

Set up external alerts (e.g., Prometheus/Grafana or Datadog) to watch:
1. **HTTP 5xx Spikes**: On `nexus-api`.
2. **Worker Queue Depth**: If RQ jobs back up, scale out `nexus-worker` containers.
3. **Agent Heartbeats**: If Agents fail to check-in repeatedly.
4. **Task Failures**: Watch the Portal or `/tasks?status=failed` for a sudden burst of task rejections (could indicate Persona Policy misconfigurations or Agent disconnections).
