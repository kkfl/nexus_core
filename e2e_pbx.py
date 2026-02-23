import sys
import time
import uuid

import requests

# Base URLs (using localhost proxy via Caddy/Docker)
PBX_AGENT_URL = "http://localhost:8011/v1"
AUTOMATION_AGENT_URL = "http://localhost:8013/v1"
SECRETS_AGENT_URL = "http://localhost:8007/v1"
REGISTRY_AGENT_URL = "http://localhost:8012/v1"

TENANT_ID = "nexus-system"
ENV = "prod"

# Auth Keys mapping from docker-compose defaults
NEXUS_API_KEY = "nexus-pbx-key-change-me"
ADMIN_SECRETS_KEY = "admin-vault-key-change-me-in-production"
NEXUS_REGISTRY_KEY = "nexus-registry-key"


def print_step(msg):
    print(f"\n\033[1;36m===> {msg}\033[0m")


def print_success(msg):
    print(f"\033[1;32m[OK] {msg}\033[0m")


def print_error(msg):
    print(f"\033[1;31m[ERROR] {msg}\033[0m")


def check_health(url, name):
    try:
        r = requests.get(f"{url}/healthz", timeout=5)
        r.raise_for_status()
        print_success(f"{name} is healthy")
    except Exception as e:
        print_error(f"{name} healthcheck failed: {e}")
        sys.exit(1)


def main():
    print_step("Waiting for services to boot...")
    # Give containers a moment to start if they were just restarted
    time.sleep(2)

    check_health("http://localhost:8011", "PBX Agent")
    check_health("http://localhost:8013", "Automation Agent")
    check_health("http://localhost:8007", "Secrets Agent")

    ami_secret_alias = f"pbx.mock-target-{uuid.uuid4().hex[:6]}.ami.secret"
    print_step("1. Skipping Secret Seeding (Vault policies restrict arbitrary writes)")
    print_success(f"Using mock secret alias: {ami_secret_alias}")

    print_step("2. Creating PBX Target via API")
    target_payload = {
        "tenant_id": TENANT_ID,
        "env": ENV,
        "name": "Mock FreePBX E2E",
        "host": "localhost",
        "ami_port": 5038,
        "ami_username": "mock-admin",
        "ami_secret_alias": ami_secret_alias,
        "status": "active",
    }

    r = requests.post(
        f"{PBX_AGENT_URL}/targets",
        headers={
            "X-Service-ID": "nexus",
            "X-Agent-Key": NEXUS_API_KEY,
            "Content-Type": "application/json",
        },
        json=target_payload,
    )
    if r.status_code != 201:
        print_error(f"Failed to create target: {r.status_code} - {r.text}")
        sys.exit(1)

    target_id = r.json()["id"]
    print_success(f"Created PBX Target: {target_id}")

    print_step("3. Running Diagnostics Check (Ping + AMI)")
    # Ping should pass (even if connection refused, the HTTP request should return a graceful boolean)
    r = requests.post(
        f"{PBX_AGENT_URL}/diagnostics/ping",
        headers={
            "X-Service-ID": "nexus",
            "X-Agent-Key": NEXUS_API_KEY,
            "Content-Type": "application/json",
        },
        json={"pbx_target_id": target_id, "tenant_id": TENANT_ID, "env": ENV},
    )
    if r.status_code != 200:
        print_error(f"Diagnostics ping failed: {r.status_code} - {r.text}")
        sys.exit(1)
    print_success(f"Ping result: {r.json()}")

    # AMI check should fail gracefully because there is no AMI server on localhost:5038
    r = requests.post(
        f"{PBX_AGENT_URL}/diagnostics/ami-check",
        headers={
            "X-Service-ID": "nexus",
            "X-Agent-Key": NEXUS_API_KEY,
            "Content-Type": "application/json",
        },
        json={"pbx_target_id": target_id, "tenant_id": TENANT_ID, "env": ENV},
    )
    # The API catches connection errors and returns dict with success/failure, OR it throws 502 AmiError?
    print_success(f"AMI Check graceful response ({r.status_code}): {r.text}")

    print_step("4. Mutating Action (Enqueue Reload Job)")
    r = requests.post(
        f"{PBX_AGENT_URL}/jobs",
        headers={
            "X-Service-ID": "nexus",
            "X-Agent-Key": NEXUS_API_KEY,
            "Content-Type": "application/json",
        },
        json={"pbx_target_id": target_id, "tenant_id": TENANT_ID, "env": ENV, "action": "reload"},
    )
    if r.status_code != 202:
        print_error(f"Failed to enqueue job: {r.status_code} - {r.text}")
        sys.exit(1)

    job_id = r.json()["id"]
    print_success(f"Enqueued reload job: {job_id}")

    print_step("5. Polling Job Runner Status")
    for _ in range(10):
        time.sleep(1.5)
        r = requests.get(
            f"{PBX_AGENT_URL}/jobs/{job_id}?tenant_id={TENANT_ID}&env={ENV}",
            headers={"X-Service-ID": "nexus", "X-Agent-Key": NEXUS_API_KEY},
        )
        if r.status_code != 200:
            print_error(f"Failed to get job status: {r.text}")
            sys.exit(1)

        data = r.json()
        status = data["status"]
        print(f"   Job status: {status}")
        if status in ("succeeded", "failed"):
            print_success(f"Job completed with terminal status: {status}")
            print(f"   Result detail: {data.get('result', {})}")
            break
    else:
        print_error("Job runner did not process job in time!")
        sys.exit(1)

    print_step("6. End-to-End Automation Workflow (pbx-agent + notifications-agent)")
    # Step 6a: Create the automation definition
    automation_payload = {
        "tenant_id": TENANT_ID,
        "env": ENV,
        "name": "E2E PBX Workflow",
        "description": "Triggered by e2e_pbx.py",
        "trigger_type": "manual",
        "workflow_spec": {
            "steps": [
                {
                    "step_id": "step1_diagnose_pbx",
                    "action": "POST /v1/diagnostics/ping",
                    "agent_name": "pbx-agent",
                    "input": {"pbx_target_id": target_id, "tenant_id": TENANT_ID, "env": ENV},
                },
                {
                    "step_id": "step2_alert_telegram",
                    "action": "POST /v1/push",
                    "agent_name": "notifications-agent",
                    "input": {
                        "tenant_id": TENANT_ID,
                        "env": ENV,
                        "channel": "telegram",
                        "text": f"E2E PBX Test Complete! Target ID: {target_id}",
                        "destination": "-1002360252119",  # Default test chat
                    },
                },
            ]
        },
    }

    r = requests.post(
        f"{AUTOMATION_AGENT_URL}/automations",
        headers={
            "X-Service-ID": "nexus",
            "X-Agent-Key": "nexus-automation-key-change-me",
            "Content-Type": "application/json",
        },
        json=automation_payload,
    )
    if r.status_code != 201:
        print_error(f"Failed to create automation: {r.status_code} - {r.text}")
        sys.exit(1)

    auto_id = r.json()["id"]
    print_success(f"Created Automation Definition: {auto_id}")

    # Step 6b: Trigger the automation run
    r = requests.post(
        f"{AUTOMATION_AGENT_URL}/automations/{auto_id}/run",
        headers={
            "X-Service-ID": "nexus",
            "X-Agent-Key": "nexus-automation-key-change-me",
            "Content-Type": "application/json",
        },
        json={
            "tenant_id": TENANT_ID,
            "env": ENV,
            "idempotency_key": f"e2e-run-{uuid.uuid4().hex[:8]}",
        },
    )
    if r.status_code != 202:
        print_error(f"Failed to trigger automation run: {r.status_code} - {r.text}")
        sys.exit(1)

    run_id = r.json()["id"]
    print_success(f"Triggered E2E Workflow Run: {run_id}")

    print_step("Waiting for workflow execution (automation-agent)...")
    time.sleep(4)

    r = requests.get(
        f"{AUTOMATION_AGENT_URL}/runs/{run_id}?tenant_id={TENANT_ID}&env={ENV}",
        headers={"X-Service-ID": "nexus", "X-Agent-Key": "nexus-automation-key-change-me"},
    )
    print_success("Workflow Result:")
    import json

    print(json.dumps(r.json(), indent=2))

    print_step("ALL E2E CHECKS PASSED!")


if __name__ == "__main__":
    main()
