#!/usr/bin/env python3
"""
Email (SMTP) smoke test via notifications-agent.

Sends a test email through the notifications pipeline:
  secrets-agent → notifications-agent → mx.gsmcall.com → recipient

Usage:
  python scripts/email_smoke_test.py --to you@example.com

Prerequisites:
  Vault must contain: smtp.host, smtp.port, smtp.username, smtp.password, smtp.from_address
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import httpx

NOTIF_BASE = "http://localhost:8008"
NOTIF_H = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": "nexus-notif-key-change-me",
    "Content-Type": "application/json",
}

VAULT_BASE = "http://localhost:8007"
VAULT_H = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": "nexus-internal-key",
}


async def check_smtp_secrets() -> bool:
    """Verify all 5 SMTP secrets exist (not their values)."""
    required = ["smtp.host", "smtp.port", "smtp.username", "smtp.password", "smtp.from_address"]
    async with httpx.AsyncClient(timeout=5) as c:
        resp = await c.get(
            f"{VAULT_BASE}/v1/secrets",
            params={"tenant_id": "nexus", "env": "prod"},
            headers=VAULT_H,
        )
        if resp.status_code != 200:
            print(f"  FAIL: vault returned {resp.status_code}")
            return False
        aliases = {s["alias"] for s in resp.json()}

    missing = [r for r in required if r not in aliases]
    if missing:
        print(f"  FAIL: missing secrets: {missing}")
        return False
    print(f"  All {len(required)} SMTP secrets present")
    return True


async def send_test_email(to_addr: str) -> bool:
    """Send a test email through notifications-agent."""
    payload = {
        "tenant_id": "nexus",
        "env": "prod",
        "severity": "info",
        "channels": ["email"],
        "subject": "Nexus Email Integration Test",
        "body": (
            "This is an automated test from the Nexus platform.\n\n"
            "If you received this email, the SMTP integration with "
            "mx.gsmcall.com is working correctly.\n\n"
            "— Nexus Core"
        ),
        "destinations": {"email": to_addr},
        "idempotency_key": str(uuid.uuid4()),
    }
    async with httpx.AsyncClient(timeout=15) as c:
        resp = await c.post(f"{NOTIF_BASE}/v1/notify", headers=NOTIF_H, json=payload)
        if resp.status_code != 202:
            print(f"  FAIL: HTTP {resp.status_code} — {resp.text[:300]}")
            return False

        job = resp.json()
        job_id = job["job_id"]
        print(f"  Accepted: job_id={job_id}")

        # Wait for async delivery
        await asyncio.sleep(8)

        # Check job status
        status_resp = await c.get(
            f"{NOTIF_BASE}/v1/notifications/{job_id}",
            headers=NOTIF_H,
        )
        if status_resp.status_code == 200:
            data = status_resp.json()
            status = data.get("status", "unknown")
            deliveries = data.get("deliveries", [])
            print(f"  Job status: {status}")
            for d in deliveries:
                print(
                    f"    channel={d['channel']} status={d['status']} msg_id={d.get('provider_msg_id', 'n/a')}"
                )
            return status == "succeeded"
        else:
            print(f"  Could not fetch job status: {status_resp.status_code}")
            return False


async def main():
    parser = argparse.ArgumentParser(description="Nexus Email Smoke Test")
    parser.add_argument("--to", required=True, help="Recipient email address")
    args = parser.parse_args()

    print("=" * 60)
    print("  Nexus Email (SMTP) Smoke Test")
    print("=" * 60)

    print("\n▸ Step 1: Check SMTP Secrets")
    secrets_ok = await check_smtp_secrets()

    if not secrets_ok:
        print("\n❌ SMTP secrets not configured. Seed them first.")
        print("NEXUS EMAIL INTEGRATION STATUS: ACTION REQUIRED")
        sys.exit(1)

    print("\n▸ Step 2: Send Test Email")
    print(f"  To: {args.to}")
    send_ok = await send_test_email(args.to)

    print("\n" + "=" * 60)
    print("  REPORT")
    print("=" * 60)
    print(
        f"  {'✅' if secrets_ok else '❌'} SMTP SECRET RESOLUTION: {'PASS' if secrets_ok else 'FAIL'}"
    )
    print(f"  {'✅' if send_ok else '❌'} EMAIL DELIVERY: {'PASS' if send_ok else 'FAIL'}")
    print()

    if secrets_ok and send_ok:
        print("NEXUS EMAIL INTEGRATION STATUS: GREEN")
    else:
        print("NEXUS EMAIL INTEGRATION STATUS: ACTION REQUIRED")

    sys.exit(0 if (secrets_ok and send_ok) else 1)


if __name__ == "__main__":
    asyncio.run(main())
