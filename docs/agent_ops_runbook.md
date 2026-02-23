# Nexus Agents — Shared Operations Runbook

## Agent Map

| Agent | Port | Vault Aliases | Provider |
|-------|------|--------------|---------|
| `agent-registry` | 8012 | N/A (system of record) | — |
| `secrets-agent` | 8007 | N/A (is the vault) | — |
| `dns-agent` | 8006 | `dns.cloudflare.api_token` | Cloudflare |
| `pbx-agent` | 8011 | `pbx.<id>.ami.secret` | FreePBX/Asterisk AMI |
| `storage-agent` | 8005 | `storage.<id>.access_key_id`, `storage.<id>.secret_access_key` | S3/MinIO |
| `monitoring-agent` | 8004 | None (pushed data only) | Nagios |
| `carrier-agent` | 8006 | `carrier.<id>.account_sid`, `carrier.<id>.auth_token` | Twilio |

---

## Internal Cross-Agent Auth

Agents use inbound auth middleware requiring `X-Service-ID` and `X-Agent-Key` headers.

*   **Key Maps:** Allowed callers are strictly defined by JSON environment variables mapped in `docker-compose.yml` (e.g., `DNS_AGENT_KEYS`, `SECRETS_AGENT_KEYS`).
*   **Default State:** Maps default to `{}`. If an agent is not in the map, it cannot call the service.
*   **Canonical Naming:** Service IDs must use `kebab-case` with hyphens (e.g., `automation-agent`, `dns-agent`), matching the exact keys defined in the `_AGENT_KEYS` maps.
*   **Adding a Caller:** To allow Agent A to call Agent B:
    1.  Add `Agent A`'s service ID and key to `Agent B`'s `_AGENT_KEYS` map in `docker-compose.yml`.
    2.  Ensure `Agent A` is correctly registered in the `agent_registry` with the `auth_secret_alias` linking to the vault key (if using the standard execution client).
    3.  Alternatively, ensure `Agent A`'s `config.py` correctly requests that specific configured key.

---

## Quick Health Check (all agents)

```bash
for port in 8004 8005 8006 8007 8008 8011 8012 8013; do
  echo -n "port $port: "
  curl -s http://localhost:$port/healthz
  echo
done
```

---

## PBX Agent Operations

The `pbx-agent` communicates with FreePBX/Asterisk via the AMI (Asterisk Manager Interface) raw TCP socket. 

*   **Port Config:** Ensure AMI is enabled in `/etc/asterisk/manager.conf` and bound to port 5038 on the target server.
*   **Diagnostics:** You can test connectivity and authentication without enqueuing a job:
    ```bash
    curl -X POST http://localhost:8011/v1/diagnostics/ping \
         -H "X-Service-ID: admin" -H "X-Agent-Key: <admin-pbx-key>" \
         -H "Content-Type: application/json" \
         -d '{"pbx_target_id": "<target_id>", "tenant_id": "nexus-system", "env": "prod"}'
    ```
*   **Job Processing:** Mutating actions (e.g., `reload`) are enqueued asynchronously. The `pbx-agent` runs an internal background task to process these. You can check the status at `/v1/jobs/<job_id>`.

---

## Registering a Secret (first time)

```bash
# Store a credential in secrets-agent
curl -X POST http://localhost:8007/v1/secrets \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: <VAULT_ADMIN_KEYS[admin]>" \
  -H "Content-Type: application/json" \
  -d '{
    "alias": "<vault-alias>",
    "tenant_id": "nexus",
    "env": "prod",
    "value": "<credential-value>",
    "description": "Human-readable description"
  }'

# Grant the agent read access (if vault policy doesn't already cover it)
curl -X POST http://localhost:8007/v1/policies \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: <VAULT_ADMIN_KEYS[admin]>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "<agent>-read-<alias>",
    "service_id": "<agent-service-id>",
    "alias_pattern": "<alias-prefix>.*",
    "actions": ["read"],
    "priority": 500
  }'
```

---

## Rotating a Credential

All agents fetch credentials at runtime — **no restart needed after rotation**.

```bash
# Find the secret ID first
curl http://localhost:8007/v1/secrets?alias=<alias> \
  -H "X-Service-ID: admin" -H "X-Agent-Key: <admin-key>"

# Rotate
curl -X PUT http://localhost:8007/v1/secrets/<secret_id>/rotate \
  -H "X-Service-ID: admin" -H "X-Agent-Key: <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{"new_value": "<new-credential>"}'
```

---

## Reading Agent Logs

All agents emit structured JSON logs via structlog:

```bash
docker compose logs <agent-name> --tail 50 --follow | \
  python -c "import sys,json; [print(json.dumps(json.loads(l),indent=2)) for l in sys.stdin if l.strip()]"
```

**Important:** Credential values never appear in logs. Tokens ≥32 chars are redacted to `[REDACTED]`.

---

## Restarting an Agent

```bash
docker compose restart <agent-name>
```

Agents are stateless in-memory — restart is always safe. In-flight async jobs (dns-agent) will be retried on next call since they are stored in Postgres with `status=pending`.

---

## Wiping and Re-running Migrations

**Development only — destructive!**
```bash
docker compose exec nexus-api alembic downgrade base
docker compose exec nexus-api alembic upgrade head
```

---

## Break-Glass: Secrets Agent Unavailable

If `secrets-agent` is down, agents that need vault credentials will return `execution_failed`.  
1. Bring secrets-agent back up: `docker compose up -d secrets-agent`  
2. No credential data is cached in other agents — they will recover automatically on next request.

**monitoring-agent** is the only agent that does not require secrets-agent and will continue operating.
