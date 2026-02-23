# pbx_agent

Production FreePBX/Asterisk integration for the Nexus multi-agent platform.

## Integration Path: AMI (Asterisk Manager Interface)

**Why AMI?**
- Present on all FreePBX installations — no extra configuration required.
- Proven protocol (20+ years of production use in Asterisk).
- Covers all V1 use cases: diagnostics, status queries, and safe mutations.
- Requires only a username/password (no SSH key exchange, no REST module).

**V1 Mutation:** `core reload` via `Action: Command` — safe and idempotent.

---

## Service Information

| Item | Value |
|------|-------|
| Port | 8011 |
| Container | `pbx-agent` |
| Mock mode | `PBX_MOCK=true` (default) — serves fixture files |
| Auth | `X-Service-ID` + `X-Agent-Key` |
| DB tables | `pbx_targets`, `pbx_jobs`, `pbx_job_results`, `pbx_audit_events` |

---

## Registering a PBX Target

```bash
curl -X POST http://localhost:8011/v1/targets \
  -H "X-Service-ID: nexus" \
  -H "X-Agent-Key: nexus-pbx-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My FreePBX",
    "tenant_id": "acme",
    "env": "prod",
    "host": "192.168.1.10",
    "ami_port": 5038,
    "ami_username": "nexus-monitor",
    "ami_secret_alias": "pbx.my-freepbx.ami.secret",
    "status": "active"
  }'
```

> `ami_secret_alias` is the key stored in `secrets-agent`. Never include the actual password here.

---

## Registering Secrets in secrets-agent

```bash
# Store the AMI password for a PBX target
curl -X POST http://localhost:8007/v1/secrets \
  -H "X-Service-ID: nexus" \
  -H "X-Agent-Key: nexus-vault-internal-key" \
  -H "Content-Type: application/json" \
  -d '{
    "alias": "pbx.my-freepbx.ami.secret",
    "tenant_id": "acme",
    "env": "prod",
    "value": "your-ami-password-here"
  }'
```

Secret aliases supported:
| Alias | Content |
|-------|---------|
| `pbx.{target_id}.ami.secret` | AMI password (required) |

---

## API Reference

### Health
```
GET /healthz        Liveness
GET /readyz         Readiness (checks DB connectivity)
GET /metrics        Request count + mode
GET /v1/capabilities
```

### Targets
```
POST  /v1/targets              Register a PBX system
GET   /v1/targets?tenant_id=   List targets
GET   /v1/targets/{id}         Get target
PATCH /v1/targets/{id}         Update host/alias/status
```

### Diagnostics (immediate, no queue)
```
POST /v1/diagnostics/ping       TCP connectivity to AMI port
POST /v1/diagnostics/ami-check  AMI login validation (auth test)
POST /v1/diagnostics/version    Asterisk version + uptime
```
Body: `{ "tenant_id", "env", "pbx_target_id" }`

### Status (read-only queries)
```
POST /v1/status/peers           SIP endpoint/peer status
POST /v1/status/registrations   Provider registration status
POST /v1/status/channels        Active channel count
POST /v1/status/uptime          Core uptime
```

### Jobs (async mutations)
```
POST /v1/jobs                   Create job (action: "reload")
GET  /v1/jobs/{id}?tenant_id=   Get job + result
```

### Audit (admin only)
```
GET /v1/audit?tenant_id=&env=   Audit trail
```

---

## FreePBX AMI Setup

1. Go to Admin → User Management → AMI Users
2. Create user (e.g. `nexus-monitor`) with password
3. Assign permissions: `Read: All`, `Write: None` for read-only monitoring
4. For reload operations: `Write: System,Dialplan`
5. Ensure AMI is enabled: `Admin → Asterisk Logfiles → AMI Settings`

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | postgresql+asyncpg://... |
| `PBX_AGENT_KEYS` | ✅ | JSON service_id→key map |
| `PBX_VAULT_AGENT_KEY` | ✅ | Key pbx-agent uses to call secrets-agent |
| `PBX_NOTIF_AGENT_KEY` | ✅ | Key pbx-agent uses to call notifications-agent |
| `PBX_MOCK` | — | `true` uses fixtures instead of live AMI |
| `REGISTRY_BASE_URL` | — | agent-registry URL |

---

## Operational Caveats (V1)

1. **One connection per operation** — AMI connect/auth/run/logoff for each call. Pooling deferred to V2.
2. **Sequential job worker** — processes up to 5 jobs per tick (configurable). No parallel per-target execution.
3. **Reload idempotency** — `core reload` is safe to repeat. No other mutations in V1.
4. **pjsip vs chan_sip** — status/peers auto-detects; chan_sip fallback included.
5. **No SSH support** — fwconsole commands via SSH deferred to V2.
