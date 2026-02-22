#!/usr/bin/env bash

source "$(dirname "$0")/../common.sh"
export CORRELATION_ID="golden-path07-$(uuidgen)"

step "Running Golden Path 07: SoR Idempotency Proof"
api_login

pv_id=$(ensure_persona "Operator - Controlled Writes" "[\"dns.upsert_record\"]" "[]")

uuid_key="golden-dup-test-key-$(uuidgen)"

# 1. Run Write Task
task_id1=$(create_task "dns.upsert_record" "{
  \"domain\": \"idempotent.local\",
  \"ip\": \"10.0.0.10\",
  \"idempotency_key\": \"$uuid_key\"
}")

wait_task_complete "$task_id1"
sleep 2

# Check Entity Version
res1=$(api_call GET "/entities?kind=dns_record&external_ref=idempotent.local")
v1=$(echo "$res1" | jq -r '.[0].version')

# 2. Re-run identical payload, same key
task_id2=$(create_task "dns.upsert_record" "{
  \"domain\": \"idempotent.local\",
  \"ip\": \"10.0.0.10\",
  \"idempotency_key\": \"$uuid_key\"
}")

wait_task_complete "$task_id2"
sleep 2

res2=$(api_call GET "/entities?kind=dns_record&external_ref=idempotent.local")
v2=$(echo "$res2" | jq -r '.[0].version')

if [ "$v1" == "$v2" ]; then
  success "Idempotency Confirmed: Same payload with same Key didn't increment Entity Version ($v1 == $v2)"
else
  fail "Idempotency failed: Expected Entity v=$v1, got v=$v2"
fi

# 3. Change payload with SAME key => Expect Conflict
task_id3=$(create_task "dns.upsert_record" "{
  \"domain\": \"idempotent.local\",
  \"ip\": \"10.0.0.99\",
  \"idempotency_key\": \"$uuid_key\"
}")

# We expect this task to fail because the Worker will intercept a SoR validation Conflict!
wait=0
status="queued"
while [ $wait -lt 10 ]; do
  status=$(api_call GET "/tasks/$task_id3" | jq -r .status || echo "error")
  if [ "$status" == "failed" ]; then
     break
  fi
  sleep 2
  wait=$((wait+2))
done

if [ "$status" == "failed" ]; then
  success "Idempotency Conflict successfully blocked a mutating write against an established key!"
else
  fail "Idempotency failed: Task should have blocked but didn't!"
fi
