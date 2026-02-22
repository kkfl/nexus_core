#!/usr/bin/env bash

source "$(dirname "$0")/../common.sh"
export CORRELATION_ID="golden-path06-$(uuidgen)"

step "Running Golden Path 06: Carrier Inventory Snapshot"
api_login

# 1. Setup Personas & Agents
pv_id=$(ensure_persona "Operator - ReadOnly Infra" "[\"carrier.snapshot.inventory\"]" "[\"dns.upsert_record\"]")
a_id=$(ensure_agent "Carrier Agent" "http://carrier-agent:8006" "[\"carrier.snapshot.inventory\", \"carrier.dids.list\", \"carrier.trunks.list\"]")
ensure_route "carrier.snapshot.inventory" "false" "[]"
ensure_default "task_type" "carrier.snapshot.inventory" "$pv_id"

# 2. Setup Carrier Target
target_id=$(api_call GET "/carrier/targets" | jq -r '.[] | select(.name=="Golden Mock Carrier") | .id' | head -n1)
if [ -z "$target_id" ]; then
  target_id=$(api_call POST "/carrier/targets" -d '{
    "name": "Golden Mock Carrier",
    "provider": "mock",
    "tags": ["golden-path"]
  }' | jq -r .id)
fi

success "Carrier Target $target_id ready"

# 3. Dispatch Inventory Task
task_id=$(create_task "carrier.snapshot.inventory" "{\"carrier_target_id\": \"$target_id\"}")

# 4. Wait & Verify
wait_task_complete "$task_id"
sleep 2 # Db flush

# 5. Assert SoR Entities Created
dids=$(api_call GET "/entities?kind=carrier_did" | jq '. | length')
trunks=$(api_call GET "/entities?kind=carrier_trunk" | jq '. | length')

if [ "$dids" -gt 0 ] && [ "$trunks" -gt 0 ]; then
  success "Carrier Entities synced to SoR! ($dids DIDs, $trunks Trunks)"
else
  fail "Carrier inventory didn't sync into Entities table! (DIDs: $dids, Trunks: $trunks)"
fi

# 6. Check Carrier Snapshots Log
snapshots=$(api_call GET "/carrier/snapshots?carrier_target_id=$target_id" | jq '. | length')
if [ "$snapshots" -gt 0 ]; then
  success "Carrier snapshot history log written."
else
  fail "No carrier snapshot log"
fi
