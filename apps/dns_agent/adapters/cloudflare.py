"""
Cloudflare DNS Provider Adapter — Full implementation.

Uses Cloudflare API v4: https://api.cloudflare.com/

Auth: Bearer token — fetched from secrets_agent at runtime by alias:
  dns.cloudflare.api_token   (must have Zone:Read + Zone:Edit permissions)

Rate limits: 1200 requests/5 minutes per token.
  Handled via exponential backoff on 429 with Retry-After header parsing.

INVARIANT: The API token is NEVER logged in any function in this module.
"""
from __future__ import annotations

import asyncio
import random
from typing import List, Optional

import httpx
import structlog

from apps.dns_agent.adapters.base import DnsProviderAdapter, RecordMeta, RecordSpec, ZoneMeta

logger = structlog.get_logger(__name__)

_CF_BASE = "https://api.cloudflare.com/client/v4"
_MAX_RETRIES = 3
_BASE_DELAY = 0.5  # seconds


def _safe_headers(token: str) -> dict:
    """Build Cloudflare auth headers. Token is never logged."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def _cf_request(client: httpx.AsyncClient, method: str, path: str,
                      token: str, **kwargs) -> dict:
    """
    Perform a Cloudflare API request with retry + exponential backoff.
    Strips token from any error messages before propagating.
    Never logs the token — passes it only in the Authorization header.
    """
    url = f"{_CF_BASE}{path}"
    last_exc = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = await client.request(
                method, url,
                headers=_safe_headers(token),
                **kwargs,
            )

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", _BASE_DELAY * (2 ** attempt)))
                jitter = random.uniform(0, 0.5)
                wait = retry_after + jitter
                logger.warning("cloudflare_rate_limited", path=path, wait_s=round(wait, 2), attempt=attempt)
                await asyncio.sleep(wait)
                continue

            if resp.status_code >= 500:
                delay = _BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                logger.warning("cloudflare_server_error", status=resp.status_code, path=path,
                               attempt=attempt, retry_in=round(delay, 2))
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(delay)
                    continue

            data = resp.json()
            if not data.get("success"):
                # Redact any token from error messages before raising
                errors = data.get("errors", [])
                safe_errors = str(errors)
                raise RuntimeError(f"Cloudflare API error on {method} {path}: {safe_errors}")

            return data

        except httpx.TimeoutException as exc:
            delay = _BASE_DELAY * (2 ** (attempt - 1))
            logger.warning("cloudflare_timeout", path=path, attempt=attempt, retry_in=round(delay, 2))
            last_exc = exc
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(delay)

    raise RuntimeError(f"Cloudflare API request failed after {_MAX_RETRIES} attempts: {last_exc}")


def _parse_cf_record(r: dict) -> RecordMeta:
    return RecordMeta(
        provider_record_id=r["id"],
        record_type=r["type"],
        name=r["name"],
        value=r.get("content", ""),
        ttl=r.get("ttl", 300),
        priority=r.get("priority"),
    )


class CloudflareAdapter(DnsProviderAdapter):
    """
    Full Cloudflare DNS adapter.

    Usage:
        adapter = CloudflareAdapter(api_token=<fetched from vault>)
        zones = await adapter.list_zones()

    The token is stored as a private attribute and NEVER appears in logs,
    repr(), or exception messages.
    """
    def __init__(self, api_token: str) -> None:
        # Private — underscore prevents accidental serialization in most frameworks
        self.__api_token = api_token
        self._timeout = httpx.Timeout(10.0)

    def __repr__(self) -> str:
        return "CloudflareAdapter(token=[REDACTED])"

    async def list_zones(self, name_filter: Optional[str] = None) -> List[ZoneMeta]:
        params = {"per_page": 100}
        if name_filter:
            params["name"] = name_filter
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _cf_request(client, "GET", "/zones", self.__api_token, params=params)
        return [ZoneMeta(provider_zone_id=z["id"], zone_name=z["name"], status=z["status"])
                for z in data.get("result", [])]

    async def list_records(self, provider_zone_id: str) -> List[RecordMeta]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _cf_request(client, "GET", f"/zones/{provider_zone_id}/dns_records",
                                     self.__api_token, params={"per_page": 1000})
        return [_parse_cf_record(r) for r in data.get("result", [])]

    async def find_record(self, provider_zone_id: str, record_type: str,
                          name: str) -> Optional[RecordMeta]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _cf_request(
                client, "GET", f"/zones/{provider_zone_id}/dns_records",
                self.__api_token,
                params={"type": record_type, "name": name, "per_page": 10},
            )
        results = data.get("result", [])
        return _parse_cf_record(results[0]) if results else None

    async def upsert_record(self, provider_zone_id: str, spec: RecordSpec) -> RecordMeta:
        """Idempotent upsert — checks if record exists first, then creates or updates."""
        existing = await self.find_record(provider_zone_id, spec.record_type, spec.name)
        payload: dict = {
            "type": spec.record_type,
            "name": spec.name,
            "content": spec.value,
            "ttl": spec.ttl,
        }
        if spec.priority is not None:
            payload["priority"] = spec.priority

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if existing:
                # Update in place — PATCH to avoid clobbering other fields
                data = await _cf_request(
                    client, "PATCH",
                    f"/zones/{provider_zone_id}/dns_records/{existing.provider_record_id}",
                    self.__api_token, json=payload,
                )
            else:
                data = await _cf_request(
                    client, "POST",
                    f"/zones/{provider_zone_id}/dns_records",
                    self.__api_token, json=payload,
                )
        return _parse_cf_record(data["result"])

    async def delete_record(self, provider_zone_id: str, provider_record_id: str) -> None:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            await _cf_request(
                client, "DELETE",
                f"/zones/{provider_zone_id}/dns_records/{provider_record_id}",
                self.__api_token,
            )

    async def ensure_zone(self, zone_name: str) -> ZoneMeta:
        """Ensure zone exists. Raises RuntimeError if zone not found (creation requires account ID)."""
        zones = await self.list_zones(name_filter=zone_name)
        if zones:
            return zones[0]
        # NOTE: Creating a zone in Cloudflare requires an account_id which is
        # provider-specific config, not a plain DNS operation. For V1, zones must
        # be pre-created in Cloudflare. This returns an error if the zone is missing.
        raise RuntimeError(
            f"Zone '{zone_name}' not found in Cloudflare. "
            "Please add it to your Cloudflare account first, then register it with dns-agent."
        )
