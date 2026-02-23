# Secrets Vault Agent

Production-grade Secrets Vault for the Nexus multi-agent platform.

## Threat Model (High Level)

| Asset | Threat | Mitigation |
|---|---|---|
| Secret values at rest | DB compromise | Envelope encryption (AES-256-GCM) — plaintext never stored |
| Master KEK | Env var exposure | Loaded from env only; never persisted; V2: KMS/HSM swap |
| Secret values in logs | Debug logging | `SafeValue` wrapper + `sanitize_dict()`; no value in any log |
| Unauthorized access | Rogue agent calls | Default-deny RBAC policy engine via `X-Service-ID`/`X-Agent-Key` |
| Audit bypass | Tampered audit logs | Audit write is in same transaction; DB-level append-only via revoke of DELETE/UPDATE |
| Secret leak via API | /list or /get returning value | `SecretMeta` schema has no value field — only `/read` endpoint decrypts |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Nexus Multi-Agent System                               │
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌────────────────────┐ │
│  │ pbx-agent│    │ dns-agent│    │ other agents...    │ │
│  └────┬─────┘    └────┬─────┘    └──────────┬─────────┘ │
│       │               │                     │            │
│       └───────────────┼─────────────────────┘            │
│             X-Service-ID + X-Agent-Key headers            │
│                       │                                   │
│               ┌───────▼──────────┐                        │
│               │  secrets-agent   │  :8007                 │
│               │  (FastAPI)       │                        │
│               ├──────────────────┤                        │
│               │  PolicyEngine    │  default-deny RBAC     │
│               │  EnvelopeCrypto  │  KEK→DEK→value         │
│               │  AuditSink       │  every access logged   │
│               └───────┬──────────┘                        │
│                       │                                   │
│               ┌───────▼──────────┐                        │
│               │  Postgres        │  vault_* tables        │
│               │  vault_secrets   │  binary blobs only     │
│               │  vault_policies  │  RBAC rules            │
│               │  vault_audit_events │ immutable log      │
│               │  vault_leases    │  TTL tracking          │
│               └──────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

---

## Module Structure

```
apps/secrets_agent/
├── main.py              # FastAPI app, health, metrics
├── models.py            # SQLAlchemy vault_* table models
├── schemas.py           # Pydantic request/response schemas
├── dependencies.py      # DB sessions, service identity, policy factory
├── crypto/
│   ├── envelope.py      # Envelope encryption (KEK → DEK → value)
│   └── redaction.py     # SafeValue, sanitize_dict
├── policy/
│   └── engine.py        # Default-deny RBAC policy engine
├── store/
│   └── postgres.py      # Secret CRUD + AbstractSecretStore interface
├── audit/
│   └── sink.py          # Immutable audit event writer
├── api/
│   ├── secrets.py       # /v1/secrets/* endpoints
│   ├── policies.py      # /v1/policies/* endpoints
│   └── audit.py         # /v1/audit endpoint
├── client/
│   └── vault_client.py  # VaultClient library for other agents
└── tests/
    ├── test_crypto.py
    ├── test_policy.py
    └── test_redaction.py
```

---

## Setup & Bootstrapping

### 1. Environment variables (already in `.env`)

```bash
# Automatically reuses NEXUS_MASTER_KEY as VAULT_MASTER_KEY
VAULT_MASTER_KEY=<same as NEXUS_MASTER_KEY>

# JSON maps — change these values in production!
VAULT_AGENT_KEYS={"nexus":"nexus-vault-internal-key","pbx-agent":"pbx-vault-key-change-me",...}
VAULT_ADMIN_KEYS={"admin":"admin-vault-key-change-me-in-production"}
```

**Generate secure keys:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Start the service

```bash
docker compose build secrets-agent
docker compose up -d secrets-agent
# Run migration (already at revision 015 after alembic upgrade head):
docker compose exec nexus-api alembic upgrade head
```

### 3. Verify it's running

```bash
curl http://localhost:8007/healthz    # → {"status":"ok","service":"secrets-agent"}
curl http://localhost:8007/readyz     # → {"status":"ready"}
# Via Caddy (same origin):
curl http://localhost/vault/healthz
```

---

## How to Add a New Agent Identity

1. Generate an API key: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Add to `VAULT_AGENT_KEYS` in `.env`: `"my-new-agent":"<generated-key>"`
3. Restart: `docker compose up -d secrets-agent`
4. Create a policy granting the agent access to specific aliases:

```bash
curl -X POST http://localhost:8007/v1/policies \
  -H "Content-Type: application/json" \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-vault-key-change-me-in-production" \
  -d '{
    "name": "my-new-agent-read",
    "service_id": "my-new-agent",
    "alias_pattern": "myagent.*",
    "actions": ["read", "list_metadata"],
    "priority": 500
  }'
```

---

## Create a Secret + Policy + Retrieve Flow

### Step 1: Create an admin policy (usually done once at setup)

```bash
curl -X POST http://localhost:8007/v1/policies \
  -H "Content-Type: application/json" \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-vault-key-change-me-in-production" \
  -d '{"name":"admin-all","service_id":"admin","alias_pattern":"*",
       "actions":["read","write","rotate","list_metadata","delete"],"priority":999}'
```

### Step 2: Create a secret (admin or operator)

```bash
curl -X POST http://localhost:8007/v1/secrets \
  -H "Content-Type: application/json" \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-vault-key-change-me-in-production" \
  -d '{"alias":"pbx.sip.trunk.password","tenant_id":"nexus","env":"prod",
       "value":"my-real-password","description":"Main SIP trunk"}'
# Response: metadata only (no value), includes id
```

### Step 3: Retrieve the secret at runtime (from an authorized agent)

```bash
# First, get the secret ID from list:
curl http://localhost:8007/v1/secrets?tenant_id=nexus&env=prod \
  -H "X-Service-ID: pbx-agent" -H "X-Agent-Key: pbx-vault-key-change-me"

# Then read the decrypted value:
curl -X POST http://localhost:8007/v1/secrets/<ID>/read \
  -H "Content-Type: application/json" \
  -H "X-Service-ID: pbx-agent" \
  -H "X-Agent-Key: pbx-vault-key-change-me" \
  -d '{"reason":"runtime sip trunk connection"}'
# Response: {"id":"...","alias":"pbx.sip.trunk.password","value":"my-real-password",...}
```

### Using the VaultClient Python library (in agent code):

```python
from apps.secrets_agent.client.vault_client import vault_client_from_env

client = vault_client_from_env()  # reads VAULT_BASE_URL, VAULT_SERVICE_ID, VAULT_AGENT_KEY
sip_password = await client.get_secret(
    "pbx.sip.trunk.password",
    tenant_id="nexus",
    env="prod",
    reason="sip_trunk_connect",
    correlation_id=request_id,
)
# Use sip_password immediately. Never cache, never log.
```

---

## Rotation

```bash
# Rotate with a new value:
curl -X POST http://localhost:8007/v1/secrets/<ID>/rotate \
  -H "Content-Type: application/json" \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-vault-key-change-me-in-production" \
  -d '{"new_value":"my-new-password-2024","reason":"quarterly rotation"}'
```

Rotation re-encrypts with a brand-new random DEK. `last_rotated_at` and `next_due_at` are updated automatically.

---

## Break-Glass Procedure

For emergency access outside normal policy:

1. Temporarily add the emergency service to `VAULT_ADMIN_KEYS` in `.env`
2. Restart secrets-agent: `docker compose up -d secrets-agent`
3. Perform the emergency read. It **will** appear in the audit log.
4. Remove the emergency key and restart immediately after.
5. Review the audit log: `curl http://localhost:8007/v1/audit`

---

## Assumptions

1. **Same Postgres instance**: vault tables use `vault_` prefix within the Nexus DB. V2: isolated DB.
2. **KEK from env**: `VAULT_MASTER_KEY` loaded from env var. V2: KMS/HSM integration.
3. **No mTLS**: Service identity via `X-Service-ID` + `X-Agent-Key` headers. V2: mTLS client certs.
4. **Secrets NEVER in RAG**: Only aliases/metadata may be embedded in RAG stores. This is a hard rule.

---

## Security Rules (Non-Negotiable)

1. Secret values are NEVER logged anywhere.
2. Secret values are NEVER returned except from `POST /v1/secrets/{id}/read`.
3. Secret values are NEVER stored in any RAG/vector/memory store.
4. Other agents store only aliases (`secret_alias`) and reference this vault at runtime.
5. Every read attempt appears in `vault_audit_events` regardless of result.
