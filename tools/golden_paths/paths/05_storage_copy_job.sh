#!/usr/bin/env bash

source "$(dirname "$0")/../common.sh"
export CORRELATION_ID="golden-path05-$(uuidgen)"

step "Running Golden Path 05: Storage Copy Job"
api_login

# 1. Setup Personas & Agents
pv_id=$(ensure_persona "Operator - Controlled Writes" "[\"storage.copy\"]" "[]")
a_id=$(ensure_agent "Storage Agent" "http://storage-agent:8005" "[\"storage.list\", \"storage.head\", \"storage.presign.get\", \"storage.presign.put\", \"storage.copy\"]")
ensure_route "storage.copy" "false" "[]"
ensure_default "task_type" "storage.copy" "$pv_id"

# 2. Setup Storage Targets
t1_id=$(api_call GET "/storage/targets" | jq -r '.[] | select(.name=="Golden Mock Storage") | .id' | head -n1)
if [ -z "$t1_id" ]; then
  t1_id=$(api_call POST "/storage/targets" -d '{
    "name": "Golden Mock Storage",
    "provider": "mock",
    "bucket_name": "golden1",
    "endpoint_url": "http://minio:9000",
    "tags": ["primary"]
  }' | jq -r .id)
fi

success "Storage Target $t1_id ready"

# 3. Seed Source Object (Agent executes against local mock paths)
step "Seeding Mock Object"
# (Mock storage agent will succeed blindly for known objects or simulate copy)

# 4. Dispatch Copy Task
task_id=$(create_task "storage.copy" "{
  \"storage_target_id\": \"$t1_id\",
  \"idempotency_key\": \"golden-copy-001\",
  \"src\": {\"key\": \"reports/2026/jan.pdf\"},
  \"dst\": {\"key\": \"archives/2026/jan.pdf\"}
}")

# 5. Wait & Verify
wait_task_complete "$task_id"

sleep 2 # Let worker JobSummary interceptor flush DB

# 6. Check canonical StorageJob table
res=$(api_call GET "/storage/jobs")
copy_jobs=$(echo "$res" | jq '[.[] | select(.task_id=='$task_id')] | length')

if [ "$copy_jobs" -gt 0 ]; then
  success "StorageJob (copy) natively tracked in the Nexus SoR!"
else
  fail "StorageJob failed to track"
fi
