#!/usr/bin/env bash

source "$(dirname "$0")/../common.sh"
export CORRELATION_ID="golden-path04-$(uuidgen)"

step "Running Golden Path 04: Monitoring Ingest -> Alert to Task"
api_login

# 1. Setup Personas & Agents
# We need Controlled Writes persona so the monitoring task CAN create a triage task
pv_id=$(ensure_persona "Operator - Controlled Writes" "[\"monitoring.ingest.nagios.statusjson\", \"monitoring.alert_to_task\"]" "[]")
a_id=$(ensure_agent "Monitoring Agent" "http://monitoring-agent:8004" "[\"monitoring.ingest.nagios.statusjson\", \"monitoring.alert_to_task\"]")
ensure_route "monitoring.ingest.nagios.statusjson" "false" "[]"
ensure_default "task_type" "monitoring.ingest.nagios.statusjson" "$pv_id"

# 2. Setup Monitoring Source
source_id="mock" # Default internal mock source for the agent

# 3. Dispatch Monitoring Ingest Task
task_id=$(create_task "monitoring.ingest.nagios.statusjson" "{\"source_id\": \"$source_id\", \"create_tasks_on_alert\": true}")

# 4. Wait & Verify Ingestion complete
wait_task_complete "$task_id"
sleep 2 # buffer for worker entity commit

# 5. Assert Mon Service Entities created
res=$(api_call GET "/entities?kind=mon_service")
services=$(echo "$res" | jq '. | length')

if [ "$services" -gt 0 ]; then
  success "Monitoring Entities persisted to SoR ($services services mapped)."
else
  fail "No mon_service entities found in Canonical DB"
fi

# 6. Assert 'triage.alert' task was spawned from the ingest's JobSummary!
triage_tasks=$(api_call GET "/tasks?type=triage.alert" | jq '. | length')
if [ "$triage_tasks" -gt 0 ]; then
  success "Found $triage_tasks dynamically spawned triage tasks from the monitoring alert!"
else
  fail "Expected triage.alert tasks to be created by the monitoring agent, but found none."
fi
