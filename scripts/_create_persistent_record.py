"""Create a persistent smoke TXT record on marinagrande.org (no delete)."""

import asyncio
import datetime
import hashlib
import hmac
from email.utils import formatdate

import httpx

VAULT_BASE_URL = "http://localhost:8007"
VAULT_H = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": "nexus-internal-key",
    "Content-Type": "application/json",
}
DME_API = "https://api.dnsmadeeasy.com/V2.0"


async def main():
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{VAULT_BASE_URL}/v1/secrets",
            params={"tenant_id": "nexus", "env": "prod"},
            headers=VAULT_H,
        )
        secrets = resp.json()
        api_id = next(s["id"] for s in secrets if s["alias"] == "dns.dnsmadeeasy.api_key")
        sec_id = next(s["id"] for s in secrets if s["alias"] == "dns.dnsmadeeasy.secret_key")
        api_key = (
            await c.post(
                f"{VAULT_BASE_URL}/v1/secrets/{api_id}/read",
                json={"reason": "smoke_persistent"},
                headers=VAULT_H,
            )
        ).json()["value"]
        secret_key = (
            await c.post(
                f"{VAULT_BASE_URL}/v1/secrets/{sec_id}/read",
                json={"reason": "smoke_persistent"},
                headers=VAULT_H,
            )
        ).json()["value"]

        stamp = formatdate(usegmt=True)
        mac = hmac.new(secret_key.encode(), stamp.encode(), hashlib.sha1).hexdigest()
        dme_h = {
            "x-dnsme-apiKey": api_key,
            "x-dnsme-requestDate": stamp,
            "x-dnsme-hmac": mac,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        payload = {
            "name": "nexus-smoke-persistent",
            "type": "TXT",
            "value": f"nexus-live-{ts}",
            "ttl": 300,
        }
        resp = await c.post(f"{DME_API}/dns/managed/6070003/records/", headers=dme_h, json=payload)
        if resp.status_code in (200, 201):
            r = resp.json()
            print(
                f'CREATED: {r["name"]}.marinagrande.org TXT "{r["value"]}" TTL={r["ttl"]}  (record_id={r["id"]})'
            )
            print("This record will persist until you delete it manually.")
        else:
            print(f"FAIL: HTTP {resp.status_code} - {resp.text[:300]}")


asyncio.run(main())
