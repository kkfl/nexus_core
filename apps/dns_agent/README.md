# DNS Agent v2

Production-grade DNS management for the Nexus multi-agent platform.

## How Nexus Calls the DNS Agent

`nexus_api` is the only authorized caller (in production). It passes:
- `X-Service-ID: nexus`
- `X-Agent-Key: <nexus-dns-agent-key from DNS_AGENT_KEYS>`
- `X-Correlation-ID: <request correlation ID>` (required for tracing)

```
nexus_api
    ↓ POST /v1/records/upsert
dns-agent:8002
    ↓ fetches credentials from secrets-agent at runtime
secrets-agent:8007
    ↓ token used for one request
Cloudflare API v4
```

## How the DNS Agent Fetches Provider Credentials

Credentials are **never** stored on disk or in env vars. They are fetched from `secrets_agent` at runtime by alias:

| Provider | Secret Alias |
|----------|-------------|
| Cloudflare | `dns.cloudflare.api_token` |
| DNSMadeEasy (stub) | `dns.dnsmadeeasy.api_key`, `dns.dnsmadeeasy.secret_key` |

The token is used for one API call then discarded. Never cached. Never logged.

## Pre-requisites: Creating Secrets Aliases

Before `dns_agent` can manage a Cloudflare zone, create the credential secret:

```bash
# Register the Cloudflare API token in secrets-agent
curl -X POST http://localhost:8007/v1/secrets \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-vault-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "alias": "dns.cloudflare.api_token",
    "tenant_id": "nexus",
    "env": "prod",
    "value": "cf-api-token-your-real-value-here",
    "description": "Cloudflare API token - Zone:Read + Zone:Edit"
  }'

# Create a vault policy so dns-agent can read it
curl -X POST http://localhost:8007/v1/policies \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-vault-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "dns-agent-read-cloudflare",
    "service_id": "dns-agent",
    "alias_pattern": "dns.*",
    "actions": ["read", "list_metadata"],
    "priority": 500
  }'
```

## Example: Create an A record for tenant X in prod

```bash
# 1. Register the zone (first time only)
curl -X POST http://localhost:8002/v1/zones \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-dns-agent-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"nexus","env":"prod","zone_name":"example.com","provider":"cloudflare"}'

# 2. Upsert an A record
curl -X POST http://localhost:8002/v1/records/upsert \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-dns-agent-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "nexus",
    "env": "prod",
    "zone": "example.com",
    "records": [{"record_type":"A","name":"api","value":"1.2.3.4","ttl":300}]
  }'
# Returns: {"job_id":"...","status":"pending","message":"Upsert job created for 1 record(s)."}

# 3. Poll for job completion
curl http://localhost:8002/v1/jobs/<job_id> \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-dns-agent-key-change-me"

# 4. Verify Nexus desired state
curl "http://localhost:8002/v1/records?tenant_id=nexus&env=prod&zone=example.com" \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-dns-agent-key-change-me"
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/zones?tenant_id=&env=` | List registered zones |
| POST | `/v1/zones` | Register a new zone |
| GET | `/v1/records?tenant_id=&env=&zone=` | List DNS records (desired state) |
| POST | `/v1/records/upsert` | Batch upsert records (async job) |
| POST | `/v1/records/delete` | Batch delete records (async job) |
| POST | `/v1/sync` | Drift detection + optional reconcile |
| GET | `/v1/jobs/{id}` | Job status |
| GET | `/v1/jobs?tenant_id=` | List jobs |
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Readiness (DB check) |
| GET | `/metrics` | Prometheus-style counters |

## Assumptions

1. **Auth**: `X-Service-ID` + `X-Agent-Key` header auth from `DNS_AGENT_KEYS` env var. V2 → mTLS.
2. **Job execution**: Background `asyncio.Task` in-process. V2 → Redis-backed workers.
3. **Cloudflare zone ownership**: Zones must be pre-created in Cloudflare. `ensure_zone` only reads, not creates.
4. **One provider per zone**: Each zone belongs to exactly one provider (stored in `dns_zones.provider`).
5. **Sync default**: `POST /v1/sync` is read-only by default. Pass `reconcile=true` to auto-apply.

## Module Structure

```
apps/dns_agent/
├── main.py          FastAPI app
├── config.py        Pydantic-settings (reads env vars)
├── models.py        SQLAlchemy: dns_zones, dns_records, dns_change_jobs, dns_audit_events
├── schemas.py       Pydantic schemas (no credentials ever)
├── auth/identity.py Service identity validation
├── store/           Postgres CRUD layer
├── adapters/        Provider adapters (Cloudflare full, DNSMadeEasy stub)
├── client/          VaultClient re-export
├── jobs/            Async job runner with retry+backoff
├── metrics.py       In-process counters
├── api/             FastAPI routers
└── tests/           Unit tests
```
