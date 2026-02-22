#!/usr/bin/env bash

set -e

# Load environment
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
else
  echo "Error: .env file not found. Copy env.example to .env and configure."
  exit 1
fi

NEXUS_API_URL=${NEXUS_API_URL:-"http://localhost:8000"}

# Global state
export TOKEN=""
export CORRELATION_ID=""

# Helper: Print step status
step() {
  echo -e "\033[1;36m==>\033[0m \033[1m$1\033[0m"
}

# Helper: Success
success() {
  echo -e "\033[1;32m[OK]\033[0m $1"
}

# Helper: Fail fast
fail() {
  echo -e "\033[1;31m[ERROR]\033[0m $1"
  exit 1
}

# Helper: API Call (with auth and correlation_id)
api_call() {
  local method=$1
  local endpoint=$2
  shift 2
  
  local auth_header=""
  if [ -n "$TOKEN" ]; then
    auth_header="-H \"Authorization: Bearer $TOKEN\""
  fi
  
  local cid_header=""
  if [ -n "$CORRELATION_ID" ]; then
    cid_header="-H \"X-Correlation-Id: $CORRELATION_ID\""
  fi

  # Execute curl and capture http code and body
  local res
  res=$(eval "curl -s -w \"\n%{http_code}\" -X $method \"$NEXUS_API_URL$endpoint\" $auth_header $cid_header -H \"Content-Type: application/json\" \"\$@\"")
  
  local http_code=$(echo "$res" | tail -n1)
  local body=$(echo "$res" | head -n-1)
  
  if [ "$http_code" -ge 400 ]; then
    echo "$body" >&2
    return 1
  fi
  
  echo "$body"
}

# Helper: Authenticate
api_login() {
  step "Authenticating with Nexus API"
  local res=$(curl -s -X POST "$NEXUS_API_URL/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=${ADMIN_EMAIL}&password=${ADMIN_PASSWORD}")
    
  export TOKEN=$(echo "$res" | jq -r .access_token)
  if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
    fail "Login failed"
  fi
  success "Logged in as ${ADMIN_EMAIL}"
}

# Ensure Persona Version exists
ensure_persona() {
  local name=$1
  local req_caps=$2 # JSON array string
  local deny_tasks=$3 # JSON array string
  
  step "Ensuring Persona: $name"
  
  # Search or create persona
  local p_id=$(api_call GET "/personas" | jq -r ".[] | select(.name==\"$name\") | .id" | head -n1)
  if [ -z "$p_id" ]; then
    p_id=$(api_call POST "/personas" -d "{\"name\": \"$name\", \"description\": \"Golden Path auto-created\", \"is_active\": true}" | jq -r .id || fail "Failed to create persona")
  fi
  
  # Ensure version 1.0
  local pv_id=$(api_call GET "/personas/$p_id/versions" | jq -r ".[] | select(.version==\"1.0\") | .id" | head -n1)
  if [ -z "$pv_id" ]; then
    pv_id=$(api_call POST "/personas/$p_id/versions" -d "{
      \"version\": \"1.0\",
      \"system_prompt\": \"You are $name.\",
      \"tools_policy\": {
        \"allowed_capabilities\": $req_caps,
        \"deny_task_types\": $deny_tasks,
        \"rag\": {\"enabled\": true, \"namespaces\": [\"global\"]}
      }
    }" | jq -r .id || fail "Failed to create persona version")
  fi
  
  success "Persona $name (Version ID: $pv_id) ready"
  echo "$pv_id"
}

# Ensure Agent exists
ensure_agent() {
  local name=$1
  local url=$2
  local caps=$3 # JSON array string
  
  step "Ensuring Agent: $name"
  local a_id=$(api_call GET "/agents" | jq -r ".[] | select(.name==\"$name\") | .id" | head -n1)
  if [ -z "$a_id" ]; then
    a_id=$(api_call POST "/agents" -d "{
      \"name\": \"$name\",
      \"base_url\": \"$url\",
      \"capabilities\": {\"capabilities\": $caps},
      \"max_concurrency\": 2,
      \"timeout_seconds\": 30
    }" | jq -r .id || fail "Failed to create agent")
  fi
  success "Agent $name (ID: $a_id) ready"
  echo "$a_id"
}

# Ensure Route
ensure_route() {
  local task_type=$1
  local needs_rag=$2
  local rag_ns=$3
  
  step "Ensuring Route: $task_type"
  api_call POST "/task-routes" -d "{
    \"task_type\": \"$task_type\",
    \"required_capabilities\": [\"$task_type\"],
    \"needs_rag\": $needs_rag,
    \"rag_namespaces\": $rag_ns,
    \"rag_top_k\": 5
  }" > /dev/null || true # Ignore conflict if exists
  success "Route $task_type ready"
}

# Ensure Persona Default
ensure_default() {
  local level=$1
  local target_id=$2
  local pv_id=$3
  
  step "Ensuring Default Binding: $level -> $target_id"
  api_call POST "/personas/defaults" -d "{
    \"level\": \"$level\",
    \"target_id\": \"$target_id\",
    \"persona_version_id\": $pv_id
  }" > /dev/null || true
  success "Default mapping established"
}

create_task() {
  local type=$1
  local payload=$2
  
  local res
  res=$(api_call POST "/tasks" -d "{
    \"type\": \"$type\",
    \"payload\": $payload
  }") || fail "Failed to create task"
  
  echo "$res" | jq -r .id
}

wait_task_complete() {
  local task_id=$1
  local max_wait=30
  local wait=0
  
  step "Waiting for task $task_id to complete"
  while [ $wait -lt $max_wait ]; do
    local status=$(api_call GET "/tasks/$task_id" | jq -r .status || echo "error")
    if [ "$status" == "succeeded" ]; then
       success "Task $task_id succeeded"
       return 0
    elif [ "$status" == "failed" ]; then
       fail "Task $task_id failed"
       return 1
    fi
    sleep 2
    wait=$((wait+2))
  done
  fail "Task $task_id timed out"
}

get_task_artifact() {
  local task_id=$1
  api_call GET "/artifacts/$task_id/download-url" || fail "Failed to get artifact"
}

assert_contains() {
  local haystack=$1
  local needle=$2
  if [[ "$haystack" == *"$needle"* ]]; then
    return 0
  else
    echo -e "\033[1;31mAssertion failed: \033[0m '$needle' not found in '$haystack'"
    exit 1
  fi
}
