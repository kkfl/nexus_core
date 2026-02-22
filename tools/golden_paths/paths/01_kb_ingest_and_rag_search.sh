#!/usr/bin/env bash

source "$(dirname "$0")/../common.sh"
export CORRELATION_ID="golden-path01-$(uuidgen)"

step "Running Golden Path 01: KB Ingest & RAG Search"
api_login

# 1. Ensure minimal persona setup so we can login and run operations generically
pv_id=$(ensure_persona "Operator - ReadOnly Infra" "[\"pbx.status\", \"storage.list\"]" "[\"dns.upsert_record\", \"storage.copy\"]")

# 2. Assert KB Source
source_id=$(api_call GET "/kb/sources" | jq -r '.[0].id')
if [ "$source_id" == "null" ]; then
  source_id=$(api_call POST "/kb/sources" -d '{"name": "Golden Path Source", "kind": "manual"}' | jq -r .id)
fi

# 3. Ingest a specific document
doc_id=$(api_call POST "/kb/documents/text" -d "{
  \"source_id\": \"$source_id\",
  \"namespace\": \"global\",
  \"title\": \"Golden Path Network Config\",
  \"text\": \"The primary DNS server for the golden path infrastructure is located at 10.99.99.1. It handles all secure communications routing for Nexus. Do NOT re-route 10.99.99 to public IPs.\"
}" | jq -r .id)

success "Ingested document $doc_id"

# 4. Wait for ingest ready
max_wait=10
wait=0
ready=false
while [ $wait -lt $max_wait ]; do
  status=$(api_call GET "/kb/documents/$doc_id" | jq -r .ingest_status)
  if [ "$status" == "ready" ]; then
    ready=true
    break
  fi
  sleep 2
  wait=$((wait+2))
done

if [ "$ready" != "true" ]; then
  fail "Document $doc_id did not reach ready state."
fi
success "Document embedded and ready."

# 5. Search KB
res=$(api_call POST "/kb/search" -d '{
  "query": "What is the primary DNS server IP for golden path?",
  "namespaces": ["global"],
  "top_k": 3,
  "min_score": 0.5
}')

chunk_text=$(echo "$res" | jq -r '.[0].text')

if [[ "$chunk_text" == *"10.99.99.1"* ]]; then
  success "RAG Search Successful! Found correct context chunk."
else
  fail "RAG Search did not return the expected context."
fi
