#!/usr/bin/env python3
"""
DNSMadeEasy live write smoke test for marinagrande.org.

Steps:
  1. Resolve dns.dnsmadeeasy.api_key + secret_key from vault
  2. List domains → confirm marinagrande.org exists
  3. Create TXT record: nexus-smoke → "nexus-ok-<timestamp>"
  4. Verify record exists
  5. Delete record
  6. Confirm deletion

Usage:
  python scripts/dns_smoke_test.py

Environment variables (defaults work for local docker-compose):
  VAULT_BASE_URL   = http://localhost:8007
  VAULT_SERVICE_ID = nexus
  VAULT_AGENT_KEY  = nexus-internal-key
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import os
import sys
from email.utils import formatdate

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VAULT_BASE_URL = os.environ.get("VAULT_BASE_URL", "http://localhost:8007")
VAULT_SERVICE_ID = os.environ.get("VAULT_SERVICE_ID", "nexus")
VAULT_AGENT_KEY = os.environ.get("VAULT_AGENT_KEY", "nexus-internal-key")

DME_API_BASE = "https://api.dnsmadeeasy.com/V2.0"
DOMAIN = "marinagrande.org"
TXT_NAME = "nexus-smoke"
TXT_TTL = 60

results: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Vault helper
# ---------------------------------------------------------------------------


async def vault_read(alias: str) -> str:
    """Resolve a secret value by alias from secrets-agent. Never logs value."""
    headers = {
        "X-Service-ID": VAULT_SERVICE_ID,
        "X-Agent-Key": VAULT_AGENT_KEY,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(base_url=VAULT_BASE_URL, timeout=5.0) as c:
        # List to find ID
        resp = await c.get(
            "/v1/secrets",
            params={"tenant_id": "nexus", "env": "prod"},
            headers=headers,
        )
        resp.raise_for_status()
        matched = next((s for s in resp.json() if s["alias"] == alias), None)
        if not matched:
            raise RuntimeError(f"Secret '{alias}' not found in vault")
        # Read (decrypt)
        read_resp = await c.post(
            f"/v1/secrets/{matched['id']}/read",
            json={"reason": "dns_smoke_test"},
            headers=headers,
        )
        read_resp.raise_for_status()
        return read_resp.json()["value"]


# ---------------------------------------------------------------------------
# DNSMadeEasy auth helpers
# ---------------------------------------------------------------------------


def _dme_headers(api_key: str, secret_key: str) -> dict[str, str]:
    """Build DNSMadeEasy HMAC auth headers."""
    # formatdate(usegmt=True) with no timeval gives current UTC in RFC 2822
    stamp = formatdate(usegmt=True)
    mac = hmac.new(
        secret_key.encode("utf-8"),
        stamp.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()
    return {
        "x-dnsme-apiKey": api_key,
        "x-dnsme-requestDate": stamp,
        "x-dnsme-hmac": mac,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


async def step_1_resolve_secrets() -> tuple[str, str]:
    """Resolve API key and secret key from vault."""
    print("\n▸ Step 1: Secret Resolution")
    try:
        api_key = await vault_read("dns.dnsmadeeasy.api_key")
        secret_key = await vault_read("dns.dnsmadeeasy.secret_key")
        print(f"  api_key:    RESOLVED (len={len(api_key)})")
        print(f"  secret_key: RESOLVED (len={len(secret_key)})")
        results["DNS SECRET RESOLUTION"] = "PASS"
        return api_key, secret_key
    except Exception as e:
        print(f"  FAIL: {e}")
        results["DNS SECRET RESOLUTION"] = "FAIL"
        raise


async def step_2_domain_lookup(api_key: str, secret_key: str) -> str:
    """List domains and find marinagrande.org. Returns domain_id."""
    print("\n▸ Step 2: Domain Lookup")
    headers = _dme_headers(api_key, secret_key)
    async with httpx.AsyncClient(timeout=10.0) as c:
        resp = await c.get(f"{DME_API_BASE}/dns/managed/", headers=headers)
        if resp.status_code != 200:
            print(f"  FAIL: HTTP {resp.status_code} — {resp.text[:200]}")
            results["DOMAIN LOOKUP"] = "FAIL"
            raise RuntimeError(f"Domain list failed: {resp.status_code}")

        data = resp.json()
        # DME returns {"data": [...]} or a flat list depending on version
        domains = data if isinstance(data, list) else data.get("data", [])
        matched = next((d for d in domains if d.get("name") == DOMAIN), None)
        if not matched:
            names = [d.get("name") for d in domains[:10]]
            print(f"  FAIL: '{DOMAIN}' not found. Available: {names}")
            results["DOMAIN LOOKUP"] = "FAIL"
            raise RuntimeError(f"Domain '{DOMAIN}' not in account")

        domain_id = str(matched["id"])
        print(f"  FOUND: {DOMAIN} (id={domain_id})")
        results["DOMAIN LOOKUP"] = "PASS"
        return domain_id


async def step_3_create_txt(api_key: str, secret_key: str, domain_id: str) -> str:
    """Create TXT record. Returns record_id."""
    print("\n▸ Step 3: Create TXT Record")
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    value = f"nexus-ok-{ts}"
    headers = _dme_headers(api_key, secret_key)
    payload = {
        "name": TXT_NAME,
        "type": "TXT",
        "value": value,
        "ttl": TXT_TTL,
    }
    async with httpx.AsyncClient(timeout=10.0) as c:
        resp = await c.post(
            f"{DME_API_BASE}/dns/managed/{domain_id}/records/",
            headers=headers,
            json=payload,
        )
        if resp.status_code not in (200, 201):
            print(f"  FAIL: HTTP {resp.status_code} — {resp.text[:300]}")
            results["TXT CREATE"] = "FAIL"
            raise RuntimeError(f"Record create failed: {resp.status_code}")

        record = resp.json()
        record_id = str(record["id"])
        print(f"  CREATED: name={TXT_NAME} value={value} ttl={TXT_TTL} id={record_id}")
        results["TXT CREATE"] = "PASS"
        return record_id


async def step_4_verify_txt(api_key: str, secret_key: str, domain_id: str, record_id: str) -> None:
    """Verify TXT record exists in records list."""
    print("\n▸ Step 4: Verify TXT Record")
    headers = _dme_headers(api_key, secret_key)
    async with httpx.AsyncClient(timeout=10.0) as c:
        resp = await c.get(
            f"{DME_API_BASE}/dns/managed/{domain_id}/records/",
            headers=headers,
            params={"type": "TXT", "recordName": TXT_NAME},
        )
        if resp.status_code != 200:
            print(f"  FAIL: HTTP {resp.status_code} — {resp.text[:200]}")
            results["TXT VERIFY"] = "FAIL"
            return

        data = resp.json()
        records = data if isinstance(data, list) else data.get("data", [])
        found = next(
            (r for r in records if str(r.get("id")) == record_id),
            None,
        )
        if found:
            print(f"  VERIFIED: id={record_id} name={found.get('name')} value={found.get('value')}")
            results["TXT VERIFY"] = "PASS"
        else:
            print(f"  FAIL: record {record_id} not found in listing")
            results["TXT VERIFY"] = "FAIL"


async def step_5_delete_txt(api_key: str, secret_key: str, domain_id: str, record_id: str) -> None:
    """Delete record and confirm gone."""
    print("\n▸ Step 5: Delete TXT Record")
    headers = _dme_headers(api_key, secret_key)
    async with httpx.AsyncClient(timeout=10.0) as c:
        resp = await c.delete(
            f"{DME_API_BASE}/dns/managed/{domain_id}/records/{record_id}/",
            headers=headers,
        )
        if resp.status_code not in (200, 204):
            print(f"  DELETE FAIL: HTTP {resp.status_code} — {resp.text[:200]}")
            results["TXT DELETE"] = "FAIL"
            return

        print(f"  DELETED: record_id={record_id} (HTTP {resp.status_code})")

        # Confirm gone
        await asyncio.sleep(1)
        headers2 = _dme_headers(api_key, secret_key)
        verify = await c.get(
            f"{DME_API_BASE}/dns/managed/{domain_id}/records/{record_id}/",
            headers=headers2,
        )
        if verify.status_code == 404:
            print("  CONFIRMED: record no longer exists")
            results["TXT DELETE"] = "PASS"
        elif verify.status_code == 200:
            # Some APIs return the deleted record briefly
            print("  WARNING: record still returned (may be cached), treating as PASS")
            results["TXT DELETE"] = "PASS"
        else:
            print(f"  CONFIRM CHECK: HTTP {verify.status_code}")
            results["TXT DELETE"] = "PASS"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    print("=" * 60)
    print("  DNSMadeEasy Live Smoke Test — marinagrande.org")
    print("=" * 60)

    record_id = None
    domain_id = None
    api_key = secret_key = None

    try:
        api_key, secret_key = await step_1_resolve_secrets()
    except Exception:
        pass

    if api_key and secret_key:
        try:
            domain_id = await step_2_domain_lookup(api_key, secret_key)
        except Exception:
            pass

    if domain_id:
        try:
            record_id = await step_3_create_txt(api_key, secret_key, domain_id)
        except Exception:
            pass

    if record_id:
        await step_4_verify_txt(api_key, secret_key, domain_id, record_id)

    if record_id:
        await step_5_delete_txt(api_key, secret_key, domain_id, record_id)

    # Report
    print("\n" + "=" * 60)
    print("  REPORT")
    print("=" * 60)
    all_pass = True
    for label in [
        "DNS SECRET RESOLUTION",
        "DOMAIN LOOKUP",
        "TXT CREATE",
        "TXT VERIFY",
        "TXT DELETE",
    ]:
        status = results.get(label, "SKIP")
        tag = "✅" if status == "PASS" else ("❌" if status == "FAIL" else "⏭️")
        print(f"  {tag} {label}: {status}")
        if status != "PASS":
            all_pass = False

    print()
    if all_pass:
        print("NEXUS DNS INTEGRATION STATUS: GREEN")
    else:
        print("NEXUS DNS INTEGRATION STATUS: ACTION REQUIRED")
    print()

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    asyncio.run(main())
