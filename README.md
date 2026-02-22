# Nexus Core V1

Nexus Core is the central orchestrator that coordinates agents and personas. It serves as the system-of-record for tasks, metadata, and audit logs.

## Architecture
- **API (nexus-api):** FastAPI service for handling user and agent requests, persona registry, and enqueuing tasks.
- **Worker (nexus-worker):** Background task runner (RQ + Redis) that dispatches tasks to agents over HTTP.
- **Portal (nexus-portal):** React (Vite) Admin Web UI for configuring agents, KB, personas, metrics, and audits.
- **Storage:** Postgres (with pgvector) for metadata/state, MinIO (S3) for artifacts.
- **Demo Agent (demo-agent):** A tiny HTTP service simulating an external agent capable of responding to dispatched tasks.

## Quickstart

### 1. Start Stack
Start the ecosystem locally using docker-compose:
```bash
cp .env.example .env
docker compose up --build -d
```

### 2. Access the Nexus Portal
The administration panel is automatically built and served via Nginx when running the stack.
- **URL**: [http://localhost:3000](http://localhost:3000)
- **Login Credentials**: `admin@local.host` | `admin` (after bootstrapping below)

### 3. Run Migrations
Run Alembic migrations to construct the database schema:
```bash
docker compose exec nexus-api alembic upgrade head
```

### 4. Setup Initial Data (Bootstrap)
We can use a simple python script to bootstrap an admin user.
```bash
docker compose exec nexus-api python -m scripts.bootstrap
```
*(You will find the generated API key and User credentials in the command output)*

## Pilot Docs in the Portal

After `docker compose up --build -d`, the `docs/` directory is mounted read-only into the `nexus-api` container.
Navigate to `http://localhost:3000/docs` in the Portal (or click **Pilot Docs** in the sidebar) to browse and render all four pilot runbook documents.

## Metrics Summary

As you log in and create tasks, lightweight telemetry is automatically written to the `metrics_events` Postgres table.
Verify events flowing live:

```bash
curl -s -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8000/metrics/summary | jq .
```

Expected response:
```json
{
  "login": 3,
  "task_create": 12,
  "task_succeeded": 11,
  "persona_policy_violation": 1
}
``` (V1)

### Credentials & Secrets Vault
Nexus no longer stores secrets in plain text. Secure credentials (like Agent API Keys for outbound connection headers) are stored in the Postgres `secrets` table, utilizing AES-GCM envelope encryption.
- **NEXUS_MASTER_KEY**: A required 32-byte base64 encoded string environment variable used as the root encryption key. Never store this in the database.
- *How to generate*: `python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"`
- Agent outbound connection API keys are returned plaintext *once* upon agent creation, then stored securely encrypted within the Nexus DB.

### Rotation Procedures
- **API Keys**: Use the `/auth/api-keys/{id}/rotate` endpoint to instantly cycle API keys. The new key is returned once, and the old key is immediately invalidated. Check the Audit Trail to confirm the rotation.
- **Secrets**: Use `/secrets/{id}` PATCH endpoint to refresh the ciphertext with a new payload, incrementing the internal `key_version`.

### Authorization & Least Privilege
The system implements Role-Based Access Control (RBAC):
- **admin**: Full system control.
- **operator**: Typical management operations (Agents, KB ingest, Task route config).
- **reader**: Read-only observability for operations.
- **agent**: Strictly walled-off telemetry (checkins and execution reporting).

### Audit Trail
All critical CRUD events and security policy evaluations are persisted to the `audit_events` table. 
- You can query `GET /audit` to correlate requests by filtering `actor_id`, `actor_type`, and `action` (e.g. `api_key_rotate`, `persona_task_type_denied`, `login_success`).

### Production Checklist
- **TLS Offloading**: Front the stack with Caddy (see `infra/Caddyfile.example`) and enforce strict secure-channel HTTPS. No raw HTTP in production.
- **Vault Strategy**: Externalize `.env` secrets.
- **Disable Docs**: Ensure `ENABLE_DOCS=false` to silence the FastAPI `/docs` open specifications.
- **Database Backups**: Since the `secrets` table holds encrypted ciphertext, be sure `NEXUS_MASTER_KEY` is backed up independently of your database volumes. Without the master key, encrypted data is forever inaccessible.

## KI Persona Policy Enforcement & End-to-End Proof

Nexus intercepts and enforces Persona limitations directly at the worker scale, before dispatching tasks to autonomous agents.

### Example: End-to-End Security Demonstration

1. **Start the localized stack** (ensuring you provided `NEXUS_MASTER_KEY` in your `.env`):
   ```bash
   docker compose up --build -d
   ```

2. **Authenticate & Define Persona (with Deny List)**:
   ```bash
   TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin@local.host&password=admin" | jq -r .access_token)

   PERSONA_ID=$(curl -s -X POST "http://localhost:8000/personas/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Restricted DNS Ops", "description": "Ops persona that CANNOT upsert records.", "is_active": true}' | jq -r .id)

   PV_ID=$(curl -s -X POST "http://localhost:8000/personas/$PERSONA_ID/versions" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version": "1.0",
       "system_prompt": "You are a DNS operator.",
       "tools_policy": {
         "allowed_capabilities": ["dns.lookup", "dns.upsert_record"],
         "deny_task_types": ["dns.upsert_record"]
       }
     }' | jq -r .id)
   ```

3. **Verify Policy Blocks Unauthorized Task**:
   ```bash
   # Create a task mapped to this restricted persona
   TASK_ID=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "dns.upsert_record",
       "persona_version_id": '$PV_ID',
       "payload": {"domain": "test.com", "ip": "1.1.1.1"}
     }' | jq -r .id)
     
   # Give the async worker a moment
   sleep 2
   
   # Check the status
   curl -s -X GET "http://localhost:8000/tasks/$TASK_ID" -H "Authorization: Bearer $TOKEN" | jq .status
   # > Expected Output: "failed" (because persona_task_type_denied triggered at the worker edge)
   ```

4. **Verify API Key Rotation Auditing**:
   ```bash
   # Generate an API key
   KEY_ID=$(curl -s -X POST "http://localhost:8000/auth/api-keys" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "test_operator", "owner_type": "user", "owner_id": 1}' | jq -r .id)

   # Rotate the key
   curl -s -X POST "http://localhost:8000/auth/api-keys/$KEY_ID/rotate" \
     -H "Authorization: Bearer $TOKEN"

   # Discover the Audit Trail reflection
   curl -s -X GET "http://localhost:8000/audit?action=api_key_rotate" \
     -H "Authorization: Bearer $TOKEN" | jq .
   ```

### 4. End-to-End Test (cURL) V1 RAG + KI Persona Policy

This proves KB ingestion, automatic embedding via fastembed, semantic search, and persona-driven RAG boundary enforcement.

#### Step A: Authenticate (Get JWT Token)
```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin@nexus.local&password=admin_password" | jq -r .access_token)
```

#### Step B: Create a Persona & Version (ALLOWS "dns.*" WITH RAG)
```bash
curl -X POST "http://localhost:8000/personas" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "DNS Administrator with KB", "description": "Persona managing DNS and allowed to search KB", "is_active": true}'

# Version 1.0 (RAG Enabled, global namespace)
curl -X POST "http://localhost:8000/personas/2/versions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "1.0",
    "system_prompt": "You are a DNS bot.",
    "tools_policy": {
      "allowed_capabilities": ["dns.lookup", "dns.upsert_record", "echo"],
      "rag": {
        "enabled": true,
        "allowed_namespaces": ["global", "persona:*"],
        "max_top_k": 3,
        "max_context_chars": 6000
      }
    }
  }'
```

#### Step C: Create a KB Source and Ingest a Document
```bash
# 1. Create a Source
curl -X POST "http://localhost:8000/kb/sources" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Manual Ingestion", "kind": "manual"}'

# 2. Ingest document via text endpoint
curl -X POST "http://localhost:8000/kb/documents/text" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": 1,
    "namespace": "global",
    "title": "Internal DNS KB",
    "text": "The A record for example.com is 192.168.1.100.\nThe backup server is 192.168.1.101."
  }'

# 3. List documents to verify ingest_status (should be "ready" after worker runs)
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/kb/documents"
```

#### Step D: Register Agents and Task Routes
```bash
# DNS Agent (ID: 2)
curl -X POST "http://localhost:8000/agents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "DNS Agent", "base_url": "http://dns-agent:8002", "capabilities": {"capabilities": ["dns.lookup", "dns.upsert_record"]}, "max_concurrency": 2, "timeout_seconds": 30}'

# Route for 'dns.lookup' requiring RAG
curl -X POST "http://localhost:8000/task-routes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_type": "dns.lookup", "required_capabilities": ["dns.lookup"], "needs_rag": true, "rag_namespaces": ["global"], "rag_top_k": 3}'
```

#### Step E: Dispatch Tasks via Worker Routing & View Result
```bash
# This will AUTO-ROUTE to the DNS agent, apply the DNS Administrator Persona
# AND the worker will pre-fetch the KB context!
curl -X POST "http://localhost:8000/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "dns.lookup", "payload": {"query": "What is the A record for example.com in our KB?", "name": "example.com", "record_type": "A"}, "persona_version_id": 2, "priority": 1}'
```
**(Wait a few seconds for the worker to process the task, then fetch artifact)**
```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/artifacts/2/download-url"
```
*Open the provided URL to see `context_received_count > 0` and the extracted KB text inside the `context` array!*

#### Negative KI Tools RAG Policy Test
```bash
# Create a persona version that DISABLES RAG
curl -X POST "http://localhost:8000/personas/2/versions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "version": "2.0",
    "system_prompt": "You are limited.",
    "tools_policy": {
      "allowed_capabilities": ["dns.lookup", "echo"],
      "rag": { "enabled": false }
    }
  }'

# Dispatch explicitly using persona version 3 (the one we just created)
curl -X POST "http://localhost:8000/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "dns.lookup", "payload": {"query": "example.com", "name": "example.com"}, "persona_version_id": 3, "priority": 1}'

# The worker will automatically mark Task as FAILED due to `persona_policy_violation`!
```

## System of Record (SoR) & Write-Back End-to-End Proof

Nexus enforces that Agents cannot write directly to databases. Instead, they **propose writes** via their task responses. Nexus Worker intercepts these, validates them against the Canonical Schema rules, applying idempotency checks, and appends immutable events.

1. **Authenticate (Get JWT Token)**
   ```bash
   TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin@local.host&password=admin" | jq -r .access_token)
   ```

2. **Register a Persona & Route for DNS Writes**
   ```bash
   # Persona
   PERSONA_ID=$(curl -s -X POST "http://localhost:8000/personas/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "DNS Ops (Write)", "description": "Ops persona that can write DNS records.", "is_active": true}' | jq -r .id)

   # Persona Version
   PV_ID=$(curl -s -X POST "http://localhost:8000/personas/$PERSONA_ID/versions" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version": "1.0",
       "system_prompt": "You are a DNS operator.",
       "tools_policy": {
         "allowed_capabilities": ["dns.lookup", "dns.upsert_record"]
       }
     }' | jq -r .id)

   # Create Route
   curl -s -X POST "http://localhost:8000/task-routes/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"task_type": "dns.upsert_record", "required_capabilities": ["dns.upsert_record"]}'
   ```

3. **Dispatch a Task with a Proposed Write (IDEMPOTENT)**
   ```bash
   # Create task
   TASK_ID=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "dns.upsert_record",
       "persona_version_id": '$PV_ID',
       "payload": {
           "name": "example.com", 
           "record_type": "A", 
           "value": "1.2.3.4", 
           "ttl": 300, 
           "idempotency_key": "idem-demo-001"
       }
     }' | jq -r .id)
     
   sleep 2
   ```

4. **Verify SoR Applied the Canonical State & Events**
   ```bash
   # Check Entities
   ENT_ID=$(curl -s -X GET "http://localhost:8000/entities?kind=dns_record" \
     -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')
     
   echo "Canonical Entity UUID: $ENT_ID"
   curl -s -X GET "http://localhost:8000/entities/$ENT_ID" -H "Authorization: Bearer $TOKEN" | jq .
   
   # Check Immutable Events (Append Only)
   curl -s -X GET "http://localhost:8000/entities/$ENT_ID/events" -H "Authorization: Bearer $TOKEN" | jq .
   ```

5. **Replay Same Idempotency Key (Conflict Test)**
   ```bash
   # Same key, Different value -> Conflict!
   TASK_ID_2=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "dns.upsert_record",
       "persona_version_id": '$PV_ID',
       "payload": {
           "name": "example.com", 
           "record_type": "A", 
           "value": "9.9.9.9",  # CHANGED VALUE
           "ttl": 300, 
           "idempotency_key": "idem-demo-001"
       }
     }' | jq -r .id)
     
   sleep 2
   curl -s -X GET "http://localhost:8000/tasks/$TASK_ID_2" -H "Authorization: Bearer $TOKEN" | jq .status
   # > Expected: "failed" (idempotency_conflict)
   ```

## PBX Agent (ReadOnly + SoR) End-to-End Proof

This demonstrates the PBX Agent operating in MOCK mode to retrieve PBX topology ("inventory snapshot") without direct state mutation, but emitting deterministic Canonical `ProposedWrites` that are transacted safely into Nexus.

1. **Authenticate (Get JWT Token)**
   ```bash
   TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin@local.host&password=admin" | jq -r .access_token)
   ```

2. **Register PBX Persona and Agent**
   ```bash
   # Create Persona (PBX Auditor)
   PERSONA_ID=$(curl -s -X POST "http://localhost:8000/personas/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "PBX Auditor", "description": "Allowed to read PBX state.", "is_active": true}' | jq -r .id)

   # Create Persona Version with required capabilities
   PV_ID=$(curl -s -X POST "http://localhost:8000/personas/$PERSONA_ID/versions" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version": "1.0",
       "system_prompt": "You audit PBX systems.",
       "tools_policy": {
         "allowed_capabilities": ["pbx.status", "pbx.channels.active", "pbx.snapshot.inventory"]
       }
     }' | jq -r .id)

   # Create Agent
   AGENT_ID=$(curl -s -X POST "http://localhost:8000/agents/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "PBX Agent",
       "base_url": "http://pbx-agent:8003",
       "capabilities": {"capabilities": ["pbx.status", "pbx.channels.active", "pbx.snapshot.inventory"]},
       "max_concurrency": 2,
       "timeout_seconds": 30
     }' | jq -r .id)
   
   # Note: The database migration (007_pbx_task_routes) already creates the required task routes automatically.
   # We just need to link our PBX Agent to the snapshot route implicitly or explicitly.
   curl -s -X PATCH "http://localhost:8000/task-routes/pbx.snapshot.inventory" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d "{\"preferred_agent_id\": $AGENT_ID}"
   ```

3. **Register PBX Target (which automatically creates the Vault Secret)**
   ```bash
   TARGET_ID=$(curl -s -X POST "http://localhost:8000/pbx/targets" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Main Asterisk",
       "ami_host": "10.0.0.50",
       "ami_port": 5038,
       "ami_username": "nexus_admin",
       "ami_secret": "SuperSecretAMI",
       "tags": ["core", "voip"]
     }' | jq -r .id)
   ```

4. **Dispatch Snapshot Task**
   ```bash
   TASK_ID=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "pbx.snapshot.inventory",
       "persona_version_id": '$PV_ID',
       "payload": {
           "pbx_target_id": "'$TARGET_ID'"
       }
     }' | jq -r .id)
     
   # Wait for worker
   sleep 3
   ```

5. **Verify PBX Snapshot and Entities!**
   ```bash
   # 1. Verify general Task Success
   curl -s -X GET "http://localhost:8000/tasks/$TASK_ID" -H "Authorization: Bearer $TOKEN" | jq .status
   
   # 2. Verify Canonical PBX Entity Updated
   curl -s -X GET "http://localhost:8000/entities?kind=pbx" -H "Authorization: Bearer $TOKEN" | jq .
   
   # 3. Verify Derived PBX Endpoints Upserted from AMI state
   curl -s -X GET "http://localhost:8000/entities?kind=pbx_endpoint" -H "Authorization: Bearer $TOKEN" | jq .
   ```

## Monitoring Agent (Ingest + Alert-to-Task) End-to-End Proof

This demonstrates the Monitoring Agent processing a `statusjson` payload, updating SoR monitoring entities, and conditionally spawning triage tasks based on KI persona allowance.

1. **Authenticate**
   ```bash
   TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin@local.host&password=admin" | jq -r .access_token)
   ```

2. **Create Monitoring Persona**
   ```bash
   PERSONA_ID=$(curl -s -X POST "http://localhost:8000/personas/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "NOC Analyst", "description": "Allowed to ingest monitoring data and create alerts.", "is_active": true}' | jq -r .id)

   # Create Persona Version (ALLOWING monitoring.alert_to_task)
   PV_ID=$(curl -s -X POST "http://localhost:8000/personas/$PERSONA_ID/versions" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version": "1.0",
       "system_prompt": "You are a NOC Analyst.",
       "tools_policy": {
         "allowed_capabilities": ["monitoring.ingest.nagios.statusjson", "monitoring.alert_to_task"]
       }
     }' | jq -r .id)
     
   # Create second Persona Version (DENYING monitoring.alert_to_task)
   PV_DENY_ID=$(curl -s -X POST "http://localhost:8000/personas/$PERSONA_ID/versions" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version": "1.1",
       "system_prompt": "You are a Junior NOC Analyst.",
       "tools_policy": {
         "allowed_capabilities": ["monitoring.ingest.nagios.statusjson"]
       }
     }' | jq -r .id)
   ```

3. **Register Monitoring Agent & Source**
   ```bash
   # Create Agent
   AGENT_ID=$(curl -s -X POST "http://localhost:8000/agents/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Monitoring Agent",
       "base_url": "http://monitoring-agent:8004",
       "capabilities": {"capabilities": ["monitoring.ingest.nagios.statusjson", "monitoring.ingest.nagios.ndjson", "monitoring.snapshot", "monitoring.alert_to_task"]},
       "max_concurrency": 2,
       "timeout_seconds": 30
     }' | jq -r .id)

   # Create Source
   SOURCE_ID=$(curl -s -X POST "http://localhost:8000/monitoring/sources" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Primary Nagios", "kind": "nagios", "tags": ["prod"]}' | jq -r .id)
   ```

4. **Dispatch Authorized Ingest Task**
   ```bash
   TASK_ID=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "monitoring.ingest.nagios.statusjson",
       "persona_version_id": '$PV_ID',
       "payload": {
           "monitoring_source_id": "'$SOURCE_ID'",
           "create_tasks_on_alert": true
       }
     }' | jq -r .id)
     
   sleep 3
   ```

5. **Verify Entities and Spawned Tasks**
   ```bash
   # Check Ingest Task Status (Expect succeeded)
   curl -s -X GET "http://localhost:8000/tasks/$TASK_ID" -H "Authorization: Bearer $TOKEN" | jq .status
   
   # Verify Canonical Entities were Created
   curl -s -X GET "http://localhost:8000/entities?kind=mon_host" -H "Authorization: Bearer $TOKEN" | jq .
   curl -s -X GET "http://localhost:8000/entities?kind=mon_service" -H "Authorization: Bearer $TOKEN" | jq .
   
   # Verify Triage Tasks Were Spawned (Because PV_ID allowed it)
   # We can check tasks looking for type=triage.alert
   curl -s -X GET "http://localhost:8000/tasks/" -H "Authorization: Bearer $TOKEN" | jq '[.[] | select(.type=="triage.alert")]'
   ```

6. **Verify Negative Control (Task Creation Blocked by Persona)**
   ```bash
   # Dispatch same payload but with PV_DENY_ID
   TASK_DENY_ID=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "monitoring.ingest.nagios.statusjson",
       "persona_version_id": '$PV_DENY_ID',
       "payload": {
           "monitoring_source_id": "'$SOURCE_ID'",
           "create_tasks_on_alert": true
       }
     }' | jq -r .id)
     
   sleep 3
   
   # Check Task Status (Expect FAILED due to SoR validation rejection on proposed_tasks)
   curl -s -X GET "http://localhost:8000/tasks/$TASK_DENY_ID" -H "Authorization: Bearer $TOKEN" | jq .status
   ```

## Storage Agent (Read/Write + SoR) End-to-End Proof

This demonstrates the Storage Agent interacting with S3-compatible storage (MinIO) handling reads (`storage.list`) and writes (`storage.copy`), while securely passing internal credentials and reporting back `storage_jobs` to the System of Record.

1. **Authenticate & Seed Mock Data**
   ```bash
   TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin@local.host&password=admin" | jq -r .access_token)
   
   # Run the mock seed script (creates mock-bucket)
   docker compose exec -e AWS_ACCESS_KEY_ID=admin -e AWS_SECRET_ACCESS_KEY=minio_pass storage-agent python /app/scripts/seed_mock_storage.py
   ```

2. **Register Persona & Storage Agent**
   ```bash
   # Create Persona (Storage Operator)
   PERSONA_ID=$(curl -s -X POST "http://localhost:8000/personas/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Storage Operator", "description": "Can read and write S3.", "is_active": true}' | jq -r .id)

   # Create Persona Version with full capabilities
   PV_ID=$(curl -s -X POST "http://localhost:8000/personas/$PERSONA_ID/versions" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version": "1.0",
       "system_prompt": "You are a Storage Operator.",
       "tools_policy": {
         "allowed_capabilities": ["storage.list", "storage.copy"]
       }
     }' | jq -r .id)

   # Create Agent
   AGENT_ID=$(curl -s -X POST "http://localhost:8000/agents/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Storage Agent",
       "base_url": "http://storage-agent:8005",
       "capabilities": {"capabilities": ["storage.list", "storage.copy"]},
       "max_concurrency": 2,
       "timeout_seconds": 30
     }' | jq -r .id)
   ```

3. **Register Storage Target**
   *(Uses the special 'mock' ID to bypass actual Vault lookup in this demo, but the API expects standard credentials)*
   ```bash
   TARGET_ID=$(curl -s -X POST "http://localhost:8000/storage/targets" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Local Minio",
       "kind": "s3",
       "endpoint_url": "http://minio:9000",
       "bucket": "mock-bucket",
       "access_key_id": "admin",
       "secret_access_key": "minio_pass",
       "base_prefix": "",
       "tags": ["minio", "local"]
     }' | jq -r .id)
   
   # We use "mock" for the target_id payload below so the agent bypasses decryption since we don't have the internal secret sync fully mocked.
   # In a real environment, you pass the TARGET_ID directly!
   ```

4. **Dispatch a Read Task (storage.list)**
   ```bash
   TASK_LIST_ID=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "storage.list",
       "persona_version_id": '$PV_ID',
       "payload": {
           "storage_target_id": "mock",
           "prefix": "",
           "max_keys": 10
       }
     }' | jq -r .id)
     
   sleep 3
   
   # Check Artifact (Agent Response)
   curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8000/artifacts/$TASK_LIST_ID/download-url"
   # The resulting JSON artifact will list the `kb/test-doc-1.txt` seeded by the script.
   ```

5. **Dispatch a Write Task (storage.copy)**
   ```bash
   TASK_COPY_ID=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "storage.copy",
       "persona_version_id": '$PV_ID',
       "payload": {
           "storage_target_id": "mock",
           "idempotency_key": "copy_demo_123",
           "src": {"key": "kb/test-doc-1.txt"},
           "dst": {"key": "kb/backup-doc-1.txt"}
       }
     }' | jq -r .id)
     
   sleep 3
   ```

6. **Verify StorageJob Tracking in SoR**
   ```bash
   # Check the Jobs Endpoint
   curl -s -X GET "http://localhost:8000/storage/jobs" -H "Authorization: Bearer $TOKEN" | jq .
   
   # You should see a "copy" job with status "succeeded" populated by the JobSummary interception!
   ```

## Carrier Agent (Inventory/Read-Only + SoR) End-to-End Proof

This demonstrates the Carrier Agent importing telecom inventory (DIDs, Trunks, CNAM/Messaging status) into Canonical SoR state, scoped via KI Personas, mimicking interaction with providers like Twilio or Telnyx and providing secure deterministic syncs.

1. **Authenticate**
   ```bash
   TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin@local.host&password=admin" | jq -r .access_token)
   ```

2. **Register Persona & Carrier Agent**
   ```bash
   # Create Persona (Telecom Auditor)
   PERSONA_ID=$(curl -s -X POST "http://localhost:8000/personas/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Telecom Auditor", "description": "Reads carrier inventory states.", "is_active": true}' | jq -r .id)

   # Create Persona Version with required capabilities
   PV_ID=$(curl -s -X POST "http://localhost:8000/personas/$PERSONA_ID/versions" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "version": "1.0",
       "system_prompt": "You are a Telecom Auditor.",
       "tools_policy": {
         "allowed_capabilities": ["carrier.snapshot.inventory", "carrier.dids.list"]
       }
     }' | jq -r .id)

   # Create Agent
   AGENT_ID=$(curl -s -X POST "http://localhost:8000/agents/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Carrier Agent",
       "base_url": "http://carrier-agent:8006",
       "capabilities": {"capabilities": ["carrier.snapshot.inventory", "carrier.dids.list", "carrier.trunks.list", "carrier.messaging.status", "carrier.cnam.status"]},
       "max_concurrency": 2,
       "timeout_seconds": 30
     }' | jq -r .id)
   ```

3. **Register Carrier Target**
   ```bash
   TARGET_ID=$(curl -s -X POST "http://localhost:8000/carrier/targets" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Mock Provider",
       "provider": "mock",
       "tags": ["primary"]
     }' | jq -r .id)
   ```

4. **Dispatch Inventory Snapshot Task**
   ```bash
   TASK_ID=$(curl -s -X POST "http://localhost:8000/tasks/" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "type": "carrier.snapshot.inventory",
       "persona_version_id": '$PV_ID',
       "payload": {
           "carrier_target_id": "'$TARGET_ID'"
       }
     }' | jq -r .id)
     
   # Give the async worker a moment to process the state
   sleep 3
   ```

5. **Verify Carrier Inventory applied to Canonical DB**
   ```bash
   # Verify the Task Success
   curl -s -X GET "http://localhost:8000/tasks/$TASK_ID" -H "Authorization: Bearer $TOKEN" | jq .status
   
   # Verify Carrier DIDs Entities 
   curl -s -X GET "http://localhost:8000/entities?kind=carrier_did" -H "Authorization: Bearer $TOKEN" | jq .
   
   # Verify Carrier Trunks Entities
   curl -s -X GET "http://localhost:8000/entities?kind=carrier_trunk" -H "Authorization: Bearer $TOKEN" | jq .
   
   # Verify Snapshot log was collected
   curl -s -X GET "http://localhost:8000/carrier/snapshots?carrier_target_id=$TARGET_ID" -H "Authorization: Bearer $TOKEN" | jq .
   ```
