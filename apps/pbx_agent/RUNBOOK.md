# pbx_agent RUNBOOK

## Service Info
- **Port:** 8011 (container: `pbx-agent`)
- **DB tables:** `pbx_targets`, `pbx_jobs`, `pbx_job_results`, `pbx_audit_events`
- **Mock mode:** `PBX_MOCK=true` → fixture files served, no live AMI connection

---

## Health Checks

```bash
curl http://localhost:8011/healthz    # liveness
curl http://localhost:8011/readyz     # readiness (checks DB)
curl http://localhost:8011/metrics    # request count
```

---

## Common Failures

### AMI Authentication Denied

**Symptom:** `ami-check` returns `{"auth_ok": false, "reason": "AMI authentication failed..."}`

**Causes:**
1. Wrong AMI password stored in secrets-agent
2. Correct alias but AMI user not enabled in FreePBX
3. AMI IP whitelist blocking pbx-agent's IP

**Fix:**
```bash
# Rotate the AMI password in secrets-agent:
curl -X PUT http://localhost:8007/v1/secrets/pbx.{TARGET}.ami.secret \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-vault-internal-key" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"acme","env":"prod","value":"new-password-here"}'
```

### AMI Connection Timeout

**Symptom:** `ping.reachable = false` or `latency_ms > 5000`

**Cause:** Network path to FreePBX host blocked or AMI disabled

**Fix:**
1. Check FreePBX AMI enabled: Admin → Asterisk Settings → AMI
2. Verify `host` on the target is correct: `PATCH /v1/targets/{id}`
3. Verify firewall allows TCP:5038 from pbx-agent container

### secrets-agent returns 404 for alias

**Symptom:** `ami-check` returns 502: `"Secret alias 'X' not found in secrets-agent"`

**Fix:** Register the secret alias first (see README.md → Registering Secrets)

---

## Job Management

### Check a specific job
```bash
curl "http://localhost:8011/v1/jobs/{JOB_ID}?tenant_id=acme" \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-pbx-key-change-me"
```

### Jobs stuck in `running`
```sql
-- Reset stuck jobs (running for > 10 min)
UPDATE pbx_jobs SET status='pending', attempts=attempts-1
WHERE status='running' AND created_at < NOW() - INTERVAL '10 minutes';
```

### Jobs stuck in `pending`
- Check container logs: `docker compose logs pbx-agent`
- Verify worker is running (lifespan starts it on startup)
- Restart: `docker compose restart pbx-agent`

---

## Credential Rotation

1. Update AMI password in FreePBX (Admin → User Management → AMI Users)
2. Update secret in secrets-agent using the PUT endpoint above
3. No pbx-agent restart required — credentials fetched per request

---

## Scaling Notes

- `JOB_WORKER_TICK_SECONDS` controls polling interval (default 3s)
- `JOB_MAX_ATTEMPTS` controls retries before final failure (default 3)
- Horizontal scaling: multiple containers safe (jobs use `SELECT FOR UPDATE SKIP LOCKED`)

---

## Viewing Audit Events

```bash
curl "http://localhost:8011/v1/audit?tenant_id=acme&env=prod&limit=20" \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-pbx-key-change-me"
```

```sql
SELECT action, result, target_id, created_at
FROM pbx_audit_events
WHERE tenant_id = 'acme'
ORDER BY created_at DESC LIMIT 20;
```
