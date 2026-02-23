# notifications-agent

The central, secure notification delivery layer for the Nexus platform.
All alerts, ops notifications, and delivery confirmations are routed through this service.
No other agent delivers notifications directly — they `POST /v1/notify` here.

---

## Overview

| Property | Value |
|----------|-------|
| Port | `8008` |
| Auth | `X-Service-ID` + `X-Agent-Key` header pair |
| Queue | DB-backed asyncio tasks (V2 upgrade path: Redis) |
| Channels | Telegram ✅, Email (SMTP) ✅, SMS (Twilio) ✅, Webhook ✅ |
| Stubs | Slack, Teams (planned V2) |

---

## Quick Start

```bash
# Start the full stack
docker-compose up notifications-agent

# Health check
curl http://localhost:8008/healthz

# Send a notification
curl -X POST http://localhost:8008/v1/notify \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-notif-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "nexus",
    "env": "prod",
    "severity": "critical",
    "template_id": "agent_down",
    "channels": ["telegram"],
    "context": {"agent": "dns-agent", "reason": "OOM"},
    "idempotency_key": "dns-down-2026-02-22T01:00:00Z"
  }'
```

---

## API Reference

### `POST /v1/notify` — Send a notification
Returns `202 Accepted` immediately. Delivery is async.

**Request body:**
```json
{
  "tenant_id": "nexus",
  "env": "prod",
  "severity": "critical",
  "channels": ["telegram", "email"],
  "template_id": "agent_down",
  "context": {"agent": "dns-agent", "reason": "OOM"},
  "idempotency_key": "<unique-per-event>",
  "correlation_id": "<optional>",
  "sensitivity": "normal",
  "destinations": {"email": "ops@example.com"}
}
```

**`severity`**: `info` | `warn` | `error` | `critical`  
**`sensitivity`**: `normal` (body stored) | `sensitive` (body hashed only)  
**`idempotency_key`**: Required. Duplicate keys within 24h return the existing job (no re-delivery).

### `GET /v1/notifications/{job_id}` — Get job status + deliveries
### `GET /v1/notifications?tenant_id=&env=&status=&limit=` — List jobs
### `POST /v1/notify/{job_id}/replay` — Re-enqueue failed job (admin only)
### `POST /v1/templates` / `GET /v1/templates` — Manage custom templates
### `POST /v1/routing-rules` / `GET /v1/routing-rules` — Manage routing rules
### `GET /v1/audit?tenant_id=&limit=` — Audit log (admin only)
### `GET /healthz` / `GET /readyz` / `GET /metrics` / `GET /capabilities`

---

## Vault Aliases

All channel credentials are fetched from `secrets_agent` at delivery time — never cached, never in env vars.

| Alias | Description |
|-------|-------------|
| `telegram.bot_token` | Telegram Bot API token |
| `telegram.default_chat_id` | Default recipient chat ID |
| `telegram.chat_ids.<group>` | Per-group chat IDs |
| `smtp.host` | SMTP server hostname |
| `smtp.port` | SMTP port (e.g. `587`) |
| `smtp.username` | SMTP auth username |
| `smtp.password` | SMTP auth password |
| `smtp.from_address` | From address |
| `sms.twilio.account_sid` | Twilio Account SID |
| `sms.twilio.auth_token` | Twilio Auth Token |
| `sms.twilio.from_number` | Twilio E.164 from number |
| `webhook.<tenant_id>.signing_secret` | HMAC-SHA256 webhook signing secret |

Seed credentials:
```bash
# Example: store Telegram token for tenant nexus, env prod
curl -X POST http://localhost:8007/v1/secrets \
  -H "X-Service-ID: admin" -H "X-Agent-Key: <admin-key>" \
  -d '{"alias": "telegram.bot_token", "tenant_id": "nexus", "env": "prod", "value": "<BOT_TOKEN>"}'
```

---

## Built-in Template Library

| `template_id` | Subject | Variables |
|--------------|---------|-----------|
| `agent_down` | 🚨 Agent Down: {agent} | `agent`, `reason`, `env` |
| `job_failed` | ⚠️ Job Failed: {job_id} | `job_id`, `service`, `error`, `env` |
| `auth_denied` | 🔒 Auth Denied: {service_id} | `service_id`, `path`, `ip` |
| `high_latency` | 🐢 High Latency: {service} | `service`, `p99_ms`, `threshold_ms`, `env` |
| `dns_drift` | 🌐 DNS Drift Detected: {zone} | `zone`, `record`, `expected`, `actual` |
| `generic` | {subject} | `subject`, `body` |

All templates auto-inject `{timestamp}` (UTC).

---

## Channel Behaviour

### Telegram
- MarkdownV2 escaping for all user content
- Truncation at 4096 chars with `…[truncated]` suffix
- Rate-limit retry on HTTP 429 (respects `Retry-After`)

### SMTP (Email)
- `aiosmtplib` async send
- HTML + `text/plain` multipart always
- `Message-ID`, `Date`, `X-Nexus-Correlation-ID` headers
- STARTTLS by default (set `use_tls=False` for port 587)

### SMS (Twilio)
- Gracefully degraded if vault secrets not present (`channel_not_configured`)
- SMS body capped at 1600 chars

### Webhook
- `POST <url>` with `Content-Type: application/json`
- `X-Nexus-Signature: sha256=<hmac>` header
- `X-Nexus-Correlation-ID` header
- Timeout: 10s; 3 retries with exponential backoff + jitter

---

## Routing Rules

If `channels` is omitted on `POST /v1/notify`, the service consults `notification_routing_rules`:

1. Exact match: `tenant_id` + `env` + `severity`
2. Wildcard fallback: same but `severity = *`
3. Built-in default: `critical` → `[telegram, email]`, others → `[telegram]`

Create a routing rule (admin only):
```json
POST /v1/routing-rules
{
  "tenant_id": "nexus",
  "env": "prod",
  "severity": "*",
  "channels": ["telegram", "webhook"],
  "config": {"webhook_url": "https://hooks.example.com/nexus"},
  "enabled": true
}
```

---

## Retry & DLQ

- Each channel delivery: up to 3 attempts, exponential backoff + jitter
- After 3 failures: job status → `failed` (queryable via `GET /v1/notifications?status=failed`)
- Replay a failed job:
  ```
  POST /v1/notify/{job_id}/replay   (admin only)
  ```
  > Cannot replay `sensitivity=sensitive` jobs — body was not stored.

---

## Security

- Auth: `X-Service-ID` + `X-Agent-Key` on every request (see `NOTIFICATIONS_AGENT_KEYS` in docker-compose)
- Sensitive mode: body stored as `sha256(body)` only; destinations stored as `sha256(destination)` always
- Credentials never logged; Telegram token is private (`__token` name-mangled)

---

## Running Tests

```bash
# Unit tests (no DB/Docker required)
pytest apps/notifications_agent/tests/ -v

# E2E integration test (requires running stack)
python e2e_notifications.py
```
