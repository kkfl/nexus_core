#!/usr/bin/env bash

source "$(dirname "$0")/../common.sh"
export CORRELATION_ID="golden-path03-$(uuidgen)"

step "Running Golden Path 03: PBX Inventory Snapshot to SoR"
api_login

# 1. Setup Personas & Agents
pv_id=$(ensure_persona "Operator - ReadOnly Infra" "[\"pbx.snapshot.inventory\"]" "[\"dns.upsert_record\"]")
a_id=$(ensure_agent "PBX Agent" "http://pbx-agent:8002" "[\"pbx.status\", \"pbx.channels.active\", \"pbx.snapshot.inventory\"]")
ensure_route "pbx.snapshot.inventory" "false" "[]"
ensure_default "task_type" "pbx.snapshot.inventory" "$pv_id"

# 2. Setup PBX Target (Mock)
target_id=$(api_call GET "/pbx/targets" | jq -r '.[] | select(.name=="Golden Mock PBX") | .id' | head -n1)
if [ -z "$target_id" ]; then
  target_id=$(api_call POST "/pbx/targets" -d '{
    "name": "Golden Mock PBX",
    "provider": "mock",
    "base_url": "http://mock-pbx",
    "tags": ["golden-path"]
  }' | jq -r .id || fail "Failed to create PBX target")
fi

success "PBX Target $target_id ready"

# 3. Dispatch PBX Snapshot Task
task_id=$(create_task "pbx.snapshot.inventory" "{\"pbx_target_id\": \"$target_id\"}")

# 4. Wait & Verify
wait_task_complete "$task_id"

# 5. Assert SoR Entities Created (Wait a brief moment for worker to save entities)
sleep 2

res=$(api_call GET "/entities?kind=pbx_endpoint")
endpoints_count=$(echo "$res" | jq '. | length')

if [ "$endpoints_count" -gt 0 ]; then
  success "PBX Entities successfully persisted to Canonical SoR (Found $endpoints_count endpoints)"
else
  fail "No pbx_endpoint entities found in SoR!"
fi
