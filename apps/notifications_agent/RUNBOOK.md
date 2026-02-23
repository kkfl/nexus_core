# Notifications Agent — Operations Runbook

## Port and Endpoints

| Endpoint | Purpose |
|----------|---------|
| `http://localhost:8008/healthz` | Liveness |
| `http://localhost:8008/readyz` | Readiness (checks DB + secrets-agent) |
| `http://localhost:8008/metrics` | In-process counters + latency |
| `http://localhost:8008/capabilities` | Channels + templates list |
| `http://localhost/notify/v1/notify` | Via Caddy reverse proxy |

---

## 1. Register Secrets in secrets-agent

### Telegram (PRIMARY channel)

```bash
# Store bot token
curl -X POST http://localhost:8007/v1/secrets \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-vault-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "alias": "telegram.bot_token",
    "tenant_id": "nexus",
    "env": "prod",
    "value": "<YOUR_BOT_TOKEN>",
    "description": "Telegram Bot API token for owner alerts"
  }'

# Store default chat ID (your chat with the bot, or a group chat ID)
curl -X POST http://localhost:8007/v1/secrets \
  -H "X-Service-ID: admin" -H "X-Agent-Key: admin-vault-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "alias": "telegram.default_chat_id",
    "tenant_id": "nexus",
    "env": "prod",
    "value": "-100<YOUR_CHAT_ID>",
    "description": "Default Telegram chat ID for owner alerts"
  }'
```

> **Tip:** To find your chat ID: message your bot, then call
> `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `chat.id`

### SMTP (Email)

```bash
for alias value in \
  "smtp.host" "mail.example.com" \
  "smtp.port" "587" \
  "smtp.username" "alerts@example.com" \
  "smtp.password" "<SMTP_PASSWORD>" \
  "smtp.from_address" "Nexus Alerts <alerts@example.com>"; do
  # Run one curl per alias
done
```

### SMS (Twilio)

```bash
# sms.twilio.account_sid, sms.twilio.auth_token, sms.twilio.from_number
```

---

## 2. Test Telegram Send (critical alert)

```bash
curl -X POST http://localhost:8008/v1/notify \
  -H "X-Service-ID: nexus" \
  -H "X-Agent-Key: nexus-notif-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "nexus",
    "env": "prod",
    "severity": "critical",
    "channels": ["telegram"],
    "template_id": "agent_down",
    "context": {"agent": "dns-agent", "reason": "test from runbook"},
    "idempotency_key": "runbook-test-001",
    "correlation_id": "runbook-corr-001"
  }'
```

Expected: `{"job_id": "...", "status": "pending", "message": "Delivery queued for 1 channel(s)."}`

Check status:
```bash
curl http://localhost:8008/v1/notifications/<job_id> \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-notif-key-change-me"
```

---

## 3. Enable Routing Rule: critical → telegram + email

```bash
curl -X POST http://localhost:8008/v1/routing-rules \
  -H "X-Service-ID: admin" \
  -H "X-Agent-Key: admin-notif-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "nexus",
    "env": "prod",
    "severity": "critical",
    "channels": ["telegram", "email"],
    "config": {},
    "enabled": true
  }'
```

---

## 4. Troubleshooting Common Failures

### 401 Unauthorized from Telegram (`error_code: 401`)
- Bot token is wrong or revoked
- Rotate the token: `BotFather → /revoke` → store new token in vault

### `chat not found` from Telegram
- Bot hasn't been added to the group/channel
- Or the chat ID is wrong — negative for groups (`-100XXXXXXXXXX`)
- Verify: `https://api.telegram.org/bot<TOKEN>/getChat?chat_id=<CHAT_ID>`

### Telegram rate limits (HTTP 429)
- Agent automatically retries with `Retry-After` header
- If sustained: you need multiple bot tokens for high-volume alerts

### Job stuck in `pending`
```bash
# Check job status
curl http://localhost:8008/v1/notifications/<job_id> \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-notif-key-change-me"

# View logs
docker compose logs notifications-agent --tail 30
```

### Job in `failed` (DLQ)
```bash
# List failed jobs
curl "http://localhost:8008/v1/notifications?tenant_id=nexus&status=failed" \
  -H "X-Service-ID: nexus" -H "X-Agent-Key: nexus-notif-key-change-me"

# Replay a failed job (admin only)
curl -X POST http://localhost:8008/v1/notify/<job_id>/replay \
  -H "X-Service-ID: admin" -H "X-Agent-Key: admin-notif-key-change-me"
```

> **Note:** Replay requires `sensitivity=normal` (body was stored). Sensitive jobs cannot be replayed automatically — resend fresh.

### secrets-agent unavailable
- SMS/Email/Telegram channels will fail vault fetch → jobs move to failed
- Check: `docker compose logs secrets-agent --tail 20`
- Once secrets-agent recovers, replay failed jobs

---

## 5. Metrics

```bash
curl http://localhost:8008/metrics
```

Key counters:
- `notification_requests_total`
- `notification_send_attempts`
- `notification_send_success`
- `notification_send_failure`
- `notification_jobs_dispatched`
- `notification_latency_p50_ms`
- `notification_latency_p99_ms`

---

## 6. Audit Log

```bash
curl "http://localhost:8008/v1/audit?tenant_id=nexus&limit=50" \
  -H "X-Service-ID: admin" -H "X-Agent-Key: admin-notif-key-change-me"
```
