#!/usr/bin/env bash

source "$(dirname "$0")/../common.sh"
export CORRELATION_ID="golden-path08-$(uuidgen)"

step "Running Golden Path 08: Audit Proof"
api_login

# Ensure the persona exists and deny is active
pv_id=$(ensure_persona "Reader - Portal View" "[]" "[\"dns.upsert_record\"]")
ensure_default "task_type" "dns.lookup" "$pv_id"

# 1. Intentionally spawn an access-denied event via Task Route checks limit
step "Triggering a security denial"
api_call POST "/tasks" -d "{
  \"type\": \"dns.upsert_record\",
  \"persona_version_id\": $pv_id,
  \"payload\": {}
}" > /dev/null || true # Ignore the HTTP 403 or failure response

sleep 2 # buffer

# 2. Query Audit Trail
res=$(api_call GET "/audits?limit=100")

# Assert counts
denials=$(echo "$res" | jq '[.[] | select(.action=="persona_task_type_denied")] | length')
logins=$(echo "$res" | jq '[.[] | select(.action=="login_success")] | length')
agent_writes=$(echo "$res" | jq '[.[] | select(.action=="entity_upsert")] | length')

success "Audit Summary:"
echo "  Logins: $logins"
echo "  Security Denials: $denials"
echo "  Entity Mutations: $agent_writes"

if [ "$logins" -gt 0 ] && [ "$denials" -gt 0 ] && [ "$agent_writes" -gt 0 ]; then
  success "Audit events cleanly tracked across User, System, and Agent actors!"
else
  fail "Missing audit traces! (Logins=$logins, Denials=$denials, Mutations=$agent_writes)"
fi
