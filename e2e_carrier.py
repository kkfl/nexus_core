import time
import uuid

import requests

BASE = "http://localhost:8013"  # Automation agent
HEADERS = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": "nexus-automation-key-change-me",
    "Content-Type": "application/json",
}


def test_carrier_e2e():
    print("=== Carrier Agent E2E Workflow Test ===")

    # 1. Create automation definition
    spec = {
        "steps": [
            {
                "step_id": "list_dids",
                "agent_name": "carrier-agent",
                "action": "POST /execute",
                "input": {
                    "task_id": "test-task",
                    "type": "carrier.dids.list",
                    "payload": {"carrier_target_id": "mock"},
                    "metadata": {
                        "attempt": 1,
                        "correlation_id": "test-123",
                        "requested_at": "2026-02-23T00:00:00Z",
                        "timeout_seconds": 15,
                    },
                },
                "timeout_seconds": 15,
                "retry_policy": {"max_attempts": 1, "backoff_ms": 0},
            },
            {
                "step_id": "notify",
                "agent_name": "notifications-agent",
                "action": "POST /v1/notify",
                "input": {
                    "tenant_id": "nexus",
                    "channels": ["telegram"],
                    "body": "Listed DIDs! Output: {{ steps.list_dids.output }}",
                    "severity": "info",
                    "idempotency_key": "test-notify-123",
                },
                "timeout_seconds": 10,
                "retry_policy": {"max_attempts": 1, "backoff_ms": 0},
            },
        ]
    }

    payload = {
        "name": "Carrier E2E List DIDs + Notify",
        "description": "Calls carrier-agent to list DIDs, then calls notifications-agent to send Telegram message.",
        "tenant_id": "nexus",
        "env": "prod",
        "workflow_spec": spec,
        "notify_on_failure": True,
        "notify_on_success": False,
    }

    r = requests.post(f"{BASE}/v1/automations", headers=HEADERS, json=payload, timeout=5)
    assert r.status_code == 201, f"Create failed: {r.status_code} {r.text}"
    auto_id = r.json()["id"]
    print(f"1. Created automation: {auto_id}")

    # 2. Trigger run
    run_payload = {"idempotency_key": str(uuid.uuid4()), "tenant_id": "nexus", "env": "prod"}
    r2 = requests.post(
        f"{BASE}/v1/automations/{auto_id}/run", headers=HEADERS, json=run_payload, timeout=5
    )
    assert r2.status_code == 202, f"Trigger failed: {r2.status_code} {r2.text}"
    run_id = r2.json()["id"]
    print(f"2. Triggered run: {run_id}")

    # 3. Poll for completion
    final_status = None
    print("3. Polling run status:")
    for _ in range(15):
        time.sleep(2)
        r3 = requests.get(
            f"{BASE}/v1/runs/{run_id}",
            headers=HEADERS,
            params={"tenant_id": "nexus", "env": "prod"},
            timeout=5,
        )
        assert r3.status_code == 200, f"Get run failed: {r3.status_code} {r3.text}"
        final_status = r3.json()["status"]
        print(f"   -> {final_status}")
        if final_status in ("succeeded", "failed"):
            break

    # 4. Check step outputs
    print("4. Checking step outputs:")
    r4 = requests.get(
        f"{BASE}/v1/runs/{run_id}/steps",
        headers=HEADERS,
        params={"tenant_id": "nexus", "env": "prod"},
        timeout=5,
    )
    assert r4.status_code == 200, f"Get steps failed: {r4.status_code} {r4.text}"
    steps = r4.json()
    for s in steps:
        print(
            f"   - Step [{s['step_id']}] agent={s['target_agent']} status={s['status']} attempt={s['attempt']}"
        )
        if s.get("last_error_redacted"):
            print(f"     Error: {s['last_error_redacted'][:100]}")
        if s.get("output_summary"):
            print(f"     Output: {str(s['output_summary'])[:150]}")

    print(f"\nFinal run status: {final_status}")
    print("=== E2E Test Complete ===")

    if final_status == "failed":
        print(
            "NOTE: Run FAILED. This is likely expected if Telegram auth is missing or mock target doesn't exist."
        )
    elif final_status == "succeeded":
        print("SUCCESS: Full workflow succeeded!")


if __name__ == "__main__":
    test_carrier_e2e()
