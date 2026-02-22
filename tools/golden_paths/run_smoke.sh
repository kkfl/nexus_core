#!/usr/bin/env bash
set -e

echo "Running Nexus V1 Release Gate Smoke Tests..."

source "$(dirname "$0")/common.sh"
export CORRELATION_ID="smoke-test-$(uuidgen)"

# 1. API Health & Ready
step "Checking API Health"
health=$(curl -s -o /dev/null -w "%{http_code}\n" "$NEXUS_API_URL/healthz")
if [ "$health" != "200" ]; then fail "API /healthz returned $health"; fi
success "API Healthy"

# 2. Authenticate
api_login

# 3. Quick KB Ingest
step "Smoke Test: KB Ingest"
source_id=$(api_call POST "/kb/sources" -d '{"name": "Smoke Test Source", "kind": "manual"}' | jq -r .id)
doc_id=$(api_call POST "/kb/documents/text" -d "{
  \"source_id\": \"$source_id\",
  \"namespace\": \"smoke-test\",
  \"title\": \"Smoke Doc\",
  \"text\": \"This is a smoke test document.\"
}" | jq -r .id)
success "Document ingested (ID: $doc_id)"

# 4. Wait & Search
sleep 3
search_res=$(api_call POST "/kb/search" -d '{"query": "Smoke test", "namespaces": ["smoke-test"], "top_k": 1, "min_score": 0.0}')
count=$(echo "$search_res" | jq '. | length')
if [ "$count" -gt 0 ]; then
  success "Search returned results"
else
  fail "KB Search returned 0 results"
fi

# 5. Check Portal UI Load
step "Checking Portal UI"
portal_status=$(curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:3000/")
if [ "$portal_status" == "200" ]; then
  success "Portal UI responded HTTP 200"
else
  fail "Portal UI failed! HTTP $portal_status"
fi

echo -e "\033[1;32mALL SMOKE TESTS PASSED [GO FOR RELEASE]\033[0m"
