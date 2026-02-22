#!/usr/bin/env bash

source "$(dirname "$0")/../common.sh"
export CORRELATION_ID="golden-path02-$(uuidgen)"

step "Running Golden Path 02: DNS Lookup with RAG Context"
api_login

# 1. Setup Personas & Agents
pv_id=$(ensure_persona "Operator - ReadOnly Infra" "[\"dns.lookup\"]" "[\"dns.upsert_record\"]")
a_id=$(ensure_agent "Demo Agent" "http://demo-agent:80" "[\"dns.lookup\"]")
ensure_route "dns.lookup" "true" "[\"global\"]"
ensure_default "task_type" "dns.lookup" "$pv_id"

# 2. Ensure context exists in KB
source_id=$(api_call GET "/kb/sources" | jq -r '.[0].id')
if [ "$source_id" == "null" ]; then
  source_id=$(api_call POST "/kb/sources" -d '{"name": "Golden Path Source", "kind": "manual"}' | jq -r .id)
fi

# Seed a record specific to this test
api_call POST "/kb/documents/text" -d "{
  \"source_id\": \"$source_id\",
  \"namespace\": \"global\",
  \"title\": \"Internal Zone Overrides\",
  \"text\": \"INTERNAL ZONE RECORD overrides: \nexample.org A 192.168.100.5\ndemo.nexus.local CNAME router1.nexus.local\"
}" > /dev/null

sleep 3 # allow worker to embed

# 3. Dispatch Task
task_id=$(create_task "dns.lookup" "{\"domain\": \"example.org\"}")

# 4. Wait & Verify
wait_task_complete "$task_id"

# 5. Check Artifact for Context count
dl_url=$(get_task_artifact "$task_id")
art_res=$(curl -s "$NEXUS_API_URL$dl_url" -H "Authorization: Bearer $TOKEN")

ctx_count=$(echo "$art_res" | jq -r '.result.context_received_count')

if [ "$ctx_count" -gt 0 ]; then
  success "RAG Context successfully injected into Agent execution (count=$ctx_count)"
else
  fail "Agent did not receive RAG context, context_count was 0"
fi
