# automation_agent RUNBOOK

## Service Information
- **Port:** 8013
- **Container:** `automation-agent`
- **DB tables:** `automation_definitions`, `automation_runs`, `automation_step_runs`, `automation_dlq`, `automation_audit_events`

---

## Health Checks

```bash
# Liveness
curl http://localhost:8013/healthz

# Readiness
curl http://localhost:8013/readyz

# Prometheus metrics
curl http://localhost:8013/metrics
```

---

## Stuck Jobs

If a run is stuck in `running`:

```sql
-- Find runs stuck > 10 mins
SELECT id, automation_id, status, started_at
FROM automation_runs
WHERE status = 'running' AND started_at < NOW() - INTERVAL '10 minutes';

-- Manually reset to pending for re-pickup
UPDATE automation_runs SET status='pending', error_summary='manually reset' WHERE id = '<run_id>';
```

Or reset via API DLQ endpoint (admin key required):
```bash
curl -X POST http://localhost:8013/v1/dlq/<run_id>/replay \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-automation-key-change-me"
```

---

## DLQ Replay

1. View DLQ entries:
```sql
SELECT d.id, d.run_id, d.failed_at, d.replay_count, r.tenant_id
FROM automation_dlq d JOIN automation_runs r ON r.id = d.run_id
ORDER BY d.failed_at DESC;
```

2. Replay via API (admin only):
```bash
curl -X POST http://localhost:8013/v1/dlq/<run_id>/replay \
  -H "X-Service-ID: admin" -H "X-Agent-Key: admin-key"
```

3. Runs marked for replay are re-queued as `pending` and picked up by the next worker tick.

> **Note:** Max DLQ replays is configurable via `DLQ_MAX_REPLAYS` env var (default 3).

---

## Disabling an Automation

```bash
curl -X PATCH "http://localhost:8013/v1/automations/<id>?tenant_id=<t>&env=<e>" \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: ..." \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

## Scaling Workers

The worker concurrency is controlled by `MAX_CONCURRENT_RUNS_GLOBAL` env var (default 10). The scheduler ticks every `CRON_TICK_INTERVAL_SECONDS` (default 10).

To scale horizontally, run multiple instances — the DB `UNIQUE` constraint on `idempotency_key` prevents duplicate runs.

---

## Viewing Audit Events

```sql
-- Last 20 events for a tenant
SELECT action, result, automation_id, run_id, created_at
FROM automation_audit_events
WHERE tenant_id = 'nexus'
ORDER BY created_at DESC LIMIT 20;
```

Or via API (admin):
```bash
curl "http://localhost:8013/v1/audit?tenant_id=nexus&env=prod&limit=20" \
  -H "X-Service-ID: admin" -H "X-Agent-Key: admin-key"
```

---

## Backup / Restore

The entire automation state lives in the shared Postgres instance (`nexus_core` DB).

```bash
# Backup automation tables
pg_dump -U nexus -d nexus_core -t 'automation_*' > automation_backup.sql

# Restore
psql -U nexus -d nexus_core < automation_backup.sql
```

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `relation "automation_definitions" does not exist` | Migration 019 not applied | Run `alembic upgrade head` from nexus-api container |
| `Could not resolve agent 'X'` | Agent not in registry | Restart nexus-api to re-seed registry |
| `Failed to retrieve auth secret` | secrets-agent unreachable or alias missing | Check secrets-agent health, verify alias in vault |
| Runs stuck in `pending` | Worker not running | Check container logs: `docker compose logs automation-agent` |
