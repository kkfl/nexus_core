# automation_agent

Production-grade recurring job scheduler and workflow execution engine for the Nexus multi-agent platform.

## Overview

`automation_agent` provides:
- **Recurring schedules** — cron expressions (`schedule_cron`) evaluated every 10 seconds.
- **Manual triggers** — `POST /v1/automations/{id}/run` with idempotency key support.
- **Sequential step execution** — calls other agents discovered via `agent_registry`. Steps execute in order; failure halts the run.
- **Retries with backoff** — per-step `retry_policy.max_attempts` and `backoff_ms`.
- **Dead Letter Queue** — failed runs are placed in DLQ and can be replayed by admins.
- **Notifications** — sends Telegram alerts via `notifications-agent` on failure (and optionally on success).
- **Full audit trail** — every create, trigger, and run outcome is logged to `automation_audit_events`.

Service port: **8013**

---

## Security Model

| Direction | What | How |
|-----------|------|-----|
| Inbound | Accept requests from Nexus/Admin | `X-Service-ID` + `X-Agent-Key` header validation |
| Outbound — Discovery | Resolve agent URLs | `agent_registry` via `AgentRegistryClient` |
| Outbound — Auth keys | Retrieve agent API keys at runtime | `secrets-agent` by alias |
| Outbound — Notifications | Telegram on success/failure | `notifications-agent` resolved via registry |

> **No hardcoded agent URLs or API keys anywhere in code.**  
> **No secrets stored in DB.** Outputs are redacted before storage.

---

## Workflow Spec

Define a workflow as a JSON object stored in `automations.workflow_spec`:

```json
{
  "steps": [
    {
      "step_id": "create_record",
      "agent_name": "dns-agent",
      "action": "POST /v1/records",
      "input": {
        "zone": "example.com",
        "name": "test-{{run_id}}",
        "type": "TXT",
        "content": "automated by nexus"
      },
      "timeout_seconds": 15,
      "retry_policy": { "max_attempts": 3, "backoff_ms": 1000 }
    },
    {
      "step_id": "notify",
      "agent_name": "notifications-agent",
      "action": "POST /v1/notify",
      "depends_on": ["create_record"],
      "input": {
        "tenant_id": "{{tenant_id}}",
        "env": "{{env}}",
        "severity": "info",
        "template_id": "generic",
        "context": {
          "subject": "DNS record created",
          "body": "Run {{run_id}} completed step create_record successfully."
        }
      }
    }
  ]
}
```

### Available Template Variables

| Variable | Description |
|----------|-------------|
| `{{run_id}}` | UUID of the current run |
| `{{tenant_id}}` | Tenant scoping the automation |
| `{{env}}` | Target environment |
| `{{now}}` | ISO-8601 UTC timestamp of run start |
| `{{steps.<step_id>.output.<field>}}` | Output of a prior step |

> V1 enforces **sequential execution** in array order. `depends_on` is informational.

---

## API Reference

### Automations
```
POST   /v1/automations              Create
GET    /v1/automations              List (tenant_id + env required)
GET    /v1/automations/{id}         Get
PATCH  /v1/automations/{id}         Update (schedule/enabled/spec)
POST   /v1/automations/{id}/run     Trigger (idempotency_key required)
```

### Runs & Steps
```
GET  /v1/runs?tenant_id=&env=       List runs
GET  /v1/runs/{run_id}              Get run
GET  /v1/runs/{run_id}/steps        Get step-level details
```

### Admin
```
POST /v1/dlq/{run_id}/replay        Replay a DLQ'd run (admin only)
GET  /v1/audit?tenant_id=&env=      Audit log (admin only)
```

### Health
```
GET /healthz   Liveness
GET /readyz    Readiness
GET /metrics   Prometheus metrics (request_count)
```

---

## Creating an Automation (Example)

```bash
curl -X POST http://localhost:8013/v1/automations \
  -H "X-Service-ID: nexus" \
  -H "X-Agent-Key: nexus-automation-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Hourly DNS Health Check",
    "tenant_id": "acme",
    "env": "prod",
    "schedule_cron": "0 * * * *",
    "notify_on_failure": true,
    "workflow_spec": {
      "steps": [...]
    }
  }'
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://...` |
| `AUTOMATION_AGENT_KEYS` | ✅ | JSON `{"nexus":"key","admin":"adminkey","vault":"vaultkey","notify":"notifykey"}` |
| `REGISTRY_BASE_URL` | ✅ | `http://agent-registry:8012` |
| `NEXUS_REGISTRY_AGENT_KEY` | ✅ | Key used to call agent-registry |

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `automation_definitions` | Stored automation specs + cron |
| `automation_runs` | Run records with status |
| `automation_step_runs` | Per-step execution records |
| `automation_dlq` | Failed runs awaiting replay |
| `automation_audit_events` | Full audit trail |
