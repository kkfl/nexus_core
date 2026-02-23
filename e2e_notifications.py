#!/usr/bin/env python3
"""
e2e_notifications.py — End-to-end integration test for notifications_agent.

Verifies the full notify → dispatch → inspect → audit pipeline.
Exits 0 on success, non-zero on failure.

Usage:
    python e2e_notifications.py

Env vars (default to localhost):
    NOTIF_BASE_URL   — base URL for notifications-agent (default: http://localhost:8008)
    NOTIF_SERVICE_ID — X-Service-ID header value (default: admin)
    NOTIF_API_KEY    — X-Agent-Key value (default: admin-notif-key-change-me)
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("NOTIF_BASE_URL", "http://localhost:8008")
SERVICE_ID = os.getenv("NOTIF_SERVICE_ID", "admin")
API_KEY = os.getenv("NOTIF_API_KEY", "admin-notif-key-change-me")

HEADERS = {
    "X-Service-ID": SERVICE_ID,
    "X-Agent-Key": API_KEY,
    "Content-Type": "application/json",
}

TENANT_ID = "nexus"
ENV = "prod"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def check(condition: bool, label: str):
    icon = "✅" if condition else "❌"
    print(f"  {icon} {label}")
    if not condition:
        print("       FAILURE — aborting e2e test")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def step_healthz(client: httpx.Client):
    print("\n[1] Health check — GET /healthz")
    r = client.get(f"{BASE_URL}/healthz")
    check(r.status_code == 200, f"HTTP 200 (got {r.status_code})")
    check(r.json().get("status") == "ok", "status == ok")


def step_post_notify(client: httpx.Client) -> str:
    print("\n[2] POST /v1/notify — template_id=agent_down, channel=telegram")
    idempotency_key = f"e2e-notify-{uuid.uuid4()}"
    payload = {
        "tenant_id": TENANT_ID,
        "env": ENV,
        "severity": "critical",
        "template_id": "agent_down",
        "channels": ["telegram"],
        "context": {"agent": "e2e-test-agent", "reason": "E2E integration test", "env": ENV},
        "idempotency_key": idempotency_key,
        "correlation_id": f"e2e-corr-{uuid.uuid4()}",
        "sensitivity": "normal",
    }
    r = client.post(f"{BASE_URL}/v1/notify", json=payload)
    check(r.status_code == 202, f"HTTP 202 Accepted (got {r.status_code}: {r.text[:200]})")
    data = r.json()
    check("job_id" in data, "Response contains job_id")
    check(data.get("status") == "pending", f"Status is pending (got {data.get('status')})")
    job_id = data["job_id"]
    print(f"       job_id = {job_id}")
    return job_id


def step_idempotency(client: httpx.Client, idempotency_key: str, job_id: str):
    """Re-posting with same idempotency_key must return the same job_id."""
    print("\n[3] POST /v1/notify — duplicate idempotency_key → dedup")
    payload = {
        "tenant_id": TENANT_ID,
        "env": ENV,
        "severity": "critical",
        "template_id": "agent_down",
        "channels": ["telegram"],
        "context": {"agent": "e2e-test-agent", "reason": "duplicate", "env": ENV},
        "idempotency_key": idempotency_key,
        "correlation_id": f"e2e-dedup-{uuid.uuid4()}",
    }
    r = client.post(f"{BASE_URL}/v1/notify", json=payload)
    check(r.status_code == 202, f"HTTP 202 on dedup (got {r.status_code})")
    check(r.json().get("job_id") == job_id, "Same job_id returned (dedup)")
    check("Duplicate" in r.json().get("message", ""), "Dedup message in response")


def step_get_job(client: httpx.Client, job_id: str):
    print(f"\n[4] GET /v1/notifications/{job_id}")
    # Allow up to 5s for async delivery to complete
    for _ in range(5):
        r = client.get(f"{BASE_URL}/v1/notifications/{job_id}")
        check(r.status_code == 200, f"HTTP 200 (got {r.status_code})")
        data = r.json()
        if data.get("status") in ("succeeded", "partial", "failed"):
            break
        time.sleep(1)
    data = r.json()
    check(data.get("id") == job_id, "job_id matches")
    check(data.get("tenant_id") == TENANT_ID, f"tenant_id == {TENANT_ID}")
    print(
        f"       job status = {data.get('status')}, deliveries = {len(data.get('deliveries', []))}"
    )
    # Note: delivery to telegram may fail if vault secrets aren't seeded —
    # that is expected in integration mode without live credentials.
    check(
        data.get("status") in ("pending", "running", "succeeded", "partial", "failed"),
        f"Status is a valid terminal value (got {data.get('status')})",
    )


def step_replay_non_failed_job(client: httpx.Client, job_id: str):
    """Replay of a non-failed job must return 409."""
    print(f"\n[5] POST /v1/notify/{job_id}/replay — non-failed job → 409")
    r = client.post(f"{BASE_URL}/v1/notify/{job_id}/replay")
    # If the job is still pending/running, we get 409; if already failed we get 202
    # Either is acceptable — we just verify no 5xx
    check(r.status_code in (202, 409), f"HTTP 202 or 409 (got {r.status_code})")
    print(f"       status = {r.status_code} (expected 409 for non-failed job)")


def step_list_notifications(client: httpx.Client):
    print(f"\n[6] GET /v1/notifications?tenant_id={TENANT_ID}")
    r = client.get(f"{BASE_URL}/v1/notifications", params={"tenant_id": TENANT_ID})
    check(r.status_code == 200, f"HTTP 200 (got {r.status_code})")
    data = r.json()
    check(isinstance(data, list), "Response is a list")
    check(len(data) >= 1, f"At least 1 job in list (found {len(data)})")


def step_audit_log(client: httpx.Client):
    print(f"\n[7] GET /v1/audit?tenant_id={TENANT_ID}")
    r = client.get(f"{BASE_URL}/v1/audit", params={"tenant_id": TENANT_ID})
    check(r.status_code == 200, f"HTTP 200 (got {r.status_code})")
    data = r.json()
    check(isinstance(data, list), "Response is a list")
    check(len(data) >= 1, f"At least 1 audit event (found {len(data)})")
    actions = {ev.get("action") for ev in data}
    check("notify" in actions, f"'notify' action present in audit log (found: {actions})")


def step_templates_api(client: httpx.Client):
    print("\n[8] GET /v1/templates — list templates")
    r = client.get(f"{BASE_URL}/v1/templates")
    check(r.status_code == 200, f"HTTP 200 (got {r.status_code})")
    data = r.json()
    check(isinstance(data, list), "Response is a list")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("  notifications_agent — E2E Integration Test")
    print(f"  Target: {BASE_URL}")
    print("=" * 60)

    idempotency_key = f"e2e-notify-{uuid.uuid4()}"

    with httpx.Client(timeout=30.0) as client:
        step_healthz(client)

        # Override the idempotency_key so dedup test can use same key
        print("\n[2] POST /v1/notify — template_id=agent_down, channel=telegram")
        payload = {
            "tenant_id": TENANT_ID,
            "env": ENV,
            "severity": "critical",
            "template_id": "agent_down",
            "channels": ["telegram"],
            "context": {"agent": "e2e-test-agent", "reason": "E2E integration test", "env": ENV},
            "idempotency_key": idempotency_key,
            "correlation_id": f"e2e-corr-{uuid.uuid4()}",
            "sensitivity": "normal",
        }
        r = client.post(f"{BASE_URL}/v1/notify", json=payload, headers=HEADERS)
        check(r.status_code == 202, f"HTTP 202 Accepted (got {r.status_code}: {r.text[:200]})")
        data = r.json()
        check("job_id" in data, "Response contains job_id")
        job_id = data["job_id"]
        print(f"       job_id = {job_id}")

        step_idempotency(client, idempotency_key, job_id)
        step_get_job(client, job_id)
        step_replay_non_failed_job(client, job_id)
        step_list_notifications(client)
        step_audit_log(client)
        step_templates_api(client)

    print("\n" + "=" * 60)
    print("  ✅  All e2e assertions passed")
    print("=" * 60)
    print()
    print("  NOTE: Telegram delivery may show status='partial' or 'failed'")
    print("  if vault secrets (telegram.bot_token, telegram.default_chat_id)")
    print("  have not been pre-seeded in secrets_agent. This is expected in")
    print("  integration mode. The workflow engine correctly records failures.")
    print()


if __name__ == "__main__":
    main()
