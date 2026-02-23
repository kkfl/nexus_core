# DNS Agent — Operations Runbook

## Deployed Endpoints

| Path | Purpose |
|------|---------|
| `http://localhost:8002/healthz` | Liveness |
| `http://localhost:8002/readyz` | Readiness (checks DB) |
| `http://localhost:8002/metrics` | Counter metrics |
| `http://localhost/dns/v1/zones` | Via Caddy |

## Symptoms & Remediation

### 1. Zone registration fails: "Zone not found in Cloudflare"

**Cause:** Zone must be pre-created in Cloudflare before it can be managed by dns-agent.  
**Fix:** Log into Cloudflare dashboard → Add Site → choose the zone name → complete setup. Then retry `POST /v1/zones`.

### 2. Upsert job stuck in `pending`

**Check job status:**
```bash
curl http://localhost:8002/v1/jobs/<job_id> \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: <key>"
```
**Likely causes:**
- `secrets-agent` unreachable → check `docker compose logs secrets-agent`
- Cloudflare API token missing or expired → check `GET /vault/v1/secrets/metadata/dns.cloudflare.api_token`  
- Cloudflare token lacks Zone:Edit permission → re-create token with correct scope

### 3. Job fails with `last_error: [REDACTED]`

The token was redacted from the error. Check real error:
```bash
docker compose logs dns-agent --tail 50 | grep dns_job
```
Errors will show structured fields: `job_id`, `attempt`, `error` (with token-shaped strings redacted).

### 4. Drift keeps appearing after reconcile

**Cause:** Another system (or Cloudflare dashboard) is modifying records outside dns-agent.  
**Fix:** Identify the external change source. Run `POST /v1/sync` with `reconcile: true` to re-apply desired state.

### 5. `readyz` returns 503

DB is unreachable.
```bash
docker compose ps postgres
docker compose logs postgres --tail 20
```

---

## Rotating the Cloudflare API Token

1. Create a new token in Cloudflare with Zone:Read + Zone:Edit  
2. Update the secret in vault:
```bash
curl -X PUT http://localhost:8007/v1/secrets/<secret_id>/rotate \
  -H "X-Service-ID: admin" -H "X-Agent-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{"new_value": "<new-cf-token>"}'
```
3. No restart needed — token is fetched at runtime on every job.

---

## Rollback a Bad Change

dns-agent stores desired state in `dns_records` table. To roll back:

1. Find the job that applied the bad change: `GET /v1/jobs?tenant_id=<tenant>&status=succeeded`  
2. Issue a delete or upsert job with the previous value  
3. The job runner will call Cloudflare to revert the live record

There is **no automatic rollback** in V1 — changes are explicit and intentional.

---

## Common Rate Limit Behavior

Cloudflare: 1200 req/5 min per token. dns-agent retries on 429 with `Retry-After` header.  
If rate limits are hit repeatedly, reduce parallelism or request a limit increase from Cloudflare.

---

## Checking Audit Events

All DNS operations are written to `dns_audit_events` table. Query directly:
```sql
SELECT * FROM dns_audit_events
WHERE tenant_id = 'nexus'
ORDER BY created_at DESC LIMIT 20;
```
