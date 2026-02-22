# Nexus Operations & Smoke Tests

## 1. Quick Validations
Run to verify basic functionality.

### Get Metrics (Prometheus Format)
```bash
curl -s http://localhost:8000/metrics | grep "nexus_requests"
```

### Rotating Agent API Keys
Use the provided `/rotate_keys.sh` to cycle an agent's outbound key without manual DB tampering (it handles the ciphertext orchestration):
```bash
# Requires admin token
./infra/prod/scripts/rotate_keys.sh "eyJhbG..." "api_key_id_string"
```

## 2. End-to-End Smoke Test (Prod deploy)
Verify the production deployment is operational by executing a full lifecycle transaction: Login > Persona config > Document Ingestion > Action Execution with Write-Back.

> Replace `https://nexus.example.com` with your production URL.

### 1. Authenticate
```bash
export URL="https://nexus.example.com"
export TOKEN=$(curl -s -X POST "$URL/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@local.host&password=admin" | jq -r .access_token)
```

### 2. Create Persona & Version
```bash
P_ID=$(curl -s -X POST "$URL/personas/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Smoke Test Persona", "description": "Testing live prod", "is_active": true}' | jq -r .id)

PV_ID=$(curl -s -X POST "$URL/personas/$P_ID/versions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "1.0",
    "system_prompt": "You are a test drone.",
    "tools_policy": {
      "allowed_capabilities": ["dns.lookup", "dns.upsert_record"]
    }
  }' | jq -r .id)
```

### 3. Ingest an Operations KB Document
```bash
SRC_ID=$(curl -s -X POST "$URL/kb/sources" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Prod Manual", "kind": "manual"}' | jq -r .id)

curl -s -X POST "$URL/kb/documents/text" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": '$SRC_ID',
    "namespace": "global",
    "title": "Config Record",
    "text": "The smoke test record value is 8.8.8.8"
  }'
```

### 4. Create a Task (DNS Upsert)
```bash
TASK_ID=$(curl -s -X POST "$URL/tasks/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "dns.upsert_record",
    "persona_version_id": '$PV_ID',
    "payload": {
        "name": "smoketest.com", 
        "record_type": "A", 
        "value": "8.8.8.8", 
        "ttl": 300, 
        "idempotency_key": "smoke-idem-prod-1"
    }
  }' | jq -r .id)
```

### 5. Verify Successful Write-Back (System of Record)
```bash
# Wait briefly for the worker to execute and confirm the write
sleep 3
# Entities should now hold the canonical system state
curl -s -X GET "$URL/entities?kind=dns_record" \
  -H "Authorization: Bearer $TOKEN" | jq .
```
*If you see `smoketest.com` present in the array, the entire stack (API, Task Queue, Worker, Agent, DB Envelope Encryption, System of Record rules) is functioning flawlessly.*
