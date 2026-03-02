"""
DNSMadeEasy adapter — Full implementation.

Uses DNSMadeEasy REST API V2.0: https://api.dnsmadeeasy.com/V2.0/

Auth: HMAC-SHA1 signing with:
  - api_key:    alias dns.dnsmadeeasy.api_key    (from secrets_agent)
  - secret_key: alias dns.dnsmadeeasy.secret_key (from secrets_agent)

Each request requires three custom headers:
  - x-dnsme-apiKey:      api_key
  - x-dnsme-requestDate: RFC 1123 datetime
  - x-dnsme-hmac:        HMAC-SHA1(secret_key, requestDate)

Rate limit: 150 requests per 5-minute rolling window.
  Handled via exponential backoff on 429 responses.

INVARIANT: The API keys are NEVER logged in any function in this module.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import hmac
import random

import httpx
import structlog

from apps.dns_agent.adapters.base import DnsProviderAdapter, RecordMeta, RecordSpec, ZoneMeta

logger = structlog.get_logger(__name__)

_DME_BASE = "https://api.dnsmadeeasy.com/V2.0"
_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # seconds — DME rate limits are tighter (150/5min)


def _hmac_headers(api_key: str, secret_key: str) -> dict[str, str]:
    """
    Build HMAC-SHA1 auth headers for DNSMadeEasy.
    Keys are never logged — used only in the Authorization headers.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    request_date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    hmac_hash = hmac.new(
        secret_key.encode("utf-8"),
        request_date.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()
    return {
        "x-dnsme-apiKey": api_key,
        "x-dnsme-requestDate": request_date,
        "x-dnsme-hmac": hmac_hash,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def _dme_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    api_key: str,
    secret_key: str,
    **kwargs,
) -> dict | list:
    """
    Perform a DNSMadeEasy API request with retry + exponential backoff.
    Strips credentials from any error messages before propagating.
    Never logs the api_key or secret_key.
    """
    url = f"{_DME_BASE}{path}"
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            # Regenerate HMAC headers on each attempt (date must be fresh)
            headers = _hmac_headers(api_key, secret_key)
            resp = await client.request(method, url, headers=headers, **kwargs)

            if resp.status_code == 429:
                delay = _BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "dme_rate_limited", path=path, wait_s=round(delay, 2), attempt=attempt
                )
                await asyncio.sleep(delay)
                continue

            if resp.status_code >= 500:
                delay = _BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.warning(
                    "dme_server_error",
                    status=resp.status_code,
                    path=path,
                    attempt=attempt,
                    retry_in=round(delay, 2),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(delay)
                    continue

            if resp.status_code == 404:
                raise httpx.HTTPStatusError(
                    f"Not found: {method} {path}",
                    request=resp.request,
                    response=resp,
                )

            if resp.status_code >= 400:
                # Safe error — never include credentials
                body = resp.text[:500]
                raise RuntimeError(
                    f"DNSMadeEasy API error {resp.status_code} on {method} {path}: {body}"
                )

            # 200-299 success
            if not resp.content:
                return {}
            return resp.json()

        except httpx.TimeoutException as exc:
            delay = _BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "dme_timeout", path=path, attempt=attempt, retry_in=round(delay, 2)
            )
            last_exc = exc
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"DNSMadeEasy API request failed after {_MAX_RETRIES} attempts: {last_exc}"
    )


def _parse_dme_record(r: dict) -> RecordMeta:
    """Convert a DME record dict to our standard RecordMeta."""
    # DME uses 'type' as the record type
    # DME record names: the 'name' field is relative to the zone
    return RecordMeta(
        provider_record_id=str(r["id"]),
        record_type=r.get("type", "A"),
        name=r.get("name", "@"),
        value=r.get("value", ""),
        ttl=r.get("ttl", 300),
        priority=r.get("mxLevel") or r.get("priority"),
    )


def _parse_dme_zone(z: dict) -> ZoneMeta:
    """Convert a DME managed domain dict to our standard ZoneMeta."""
    return ZoneMeta(
        provider_zone_id=str(z["id"]),
        zone_name=z.get("name", ""),
        status="active",
    )


class DNSMadeEasyAdapter(DnsProviderAdapter):
    """
    Full DNSMadeEasy DNS adapter.

    Usage:
        adapter = DNSMadeEasyAdapter(api_key=<from vault>, secret_key=<from vault>)
        zones = await adapter.list_zones()

    The keys are stored as private attributes and NEVER appear in logs,
    repr(), or exception messages.
    """

    def __init__(self, api_key: str, secret_key: str) -> None:
        self.__api_key = api_key
        self.__secret_key = secret_key
        self._timeout = httpx.Timeout(15.0)

    def __repr__(self) -> str:
        return "DNSMadeEasyAdapter(credentials=[REDACTED])"

    async def list_zones(self, name_filter: str | None = None) -> list[ZoneMeta]:
        """List all managed domains from DNSMadeEasy."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _dme_request(
                client, "GET", "/dns/managed/", self.__api_key, self.__secret_key
            )

        # DME returns {"data": [...]} for paginated endpoints
        domains = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(domains, list):
            domains = []

        zones = [_parse_dme_zone(z) for z in domains]

        if name_filter:
            zones = [z for z in zones if z.zone_name == name_filter.lower().strip(".")]

        return zones

    async def list_records(self, provider_zone_id: str) -> list[RecordMeta]:
        """List all DNS records for a managed domain."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _dme_request(
                client,
                "GET",
                f"/dns/managed/{provider_zone_id}/records/",
                self.__api_key,
                self.__secret_key,
            )

        records = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(records, list):
            records = []

        return [_parse_dme_record(r) for r in records]

    async def find_record(
        self, provider_zone_id: str, record_type: str, name: str
    ) -> RecordMeta | None:
        """Find a specific record by type and name within a zone."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _dme_request(
                client,
                "GET",
                f"/dns/managed/{provider_zone_id}/records/",
                self.__api_key,
                self.__secret_key,
                params={"type": record_type, "recordName": name},
            )

        records = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(records, list) or not records:
            return None

        # Filter for exact match on type + name
        for r in records:
            if r.get("type") == record_type and r.get("name", "").lower() == name.lower():
                return _parse_dme_record(r)

        return _parse_dme_record(records[0]) if records else None

    async def upsert_record(self, provider_zone_id: str, spec: RecordSpec) -> RecordMeta:
        """Idempotent upsert — checks if record exists first, then creates or updates."""
        existing = await self.find_record(provider_zone_id, spec.record_type, spec.name)

        payload: dict = {
            "type": spec.record_type,
            "name": spec.name,
            "value": spec.value,
            "ttl": spec.ttl,
            "gtdLocation": "DEFAULT",
        }
        if spec.priority is not None and spec.record_type in ("MX", "SRV"):
            payload["mxLevel"] = spec.priority

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if existing:
                # Update in place — PUT to the record ID
                payload["id"] = int(existing.provider_record_id)
                data = await _dme_request(
                    client,
                    "PUT",
                    f"/dns/managed/{provider_zone_id}/records/{existing.provider_record_id}/",
                    self.__api_key,
                    self.__secret_key,
                    json=payload,
                )
            else:
                # Create new record
                data = await _dme_request(
                    client,
                    "POST",
                    f"/dns/managed/{provider_zone_id}/records/",
                    self.__api_key,
                    self.__secret_key,
                    json=payload,
                )

        if isinstance(data, dict) and "id" in data:
            return _parse_dme_record(data)

        # DME sometimes returns empty on PUT success — re-fetch
        updated = await self.find_record(provider_zone_id, spec.record_type, spec.name)
        if updated:
            return updated
        raise RuntimeError(f"Upsert succeeded but record not found: {spec.record_type} {spec.name}")

    async def delete_record(self, provider_zone_id: str, provider_record_id: str) -> None:
        """Delete a DNS record by its DME record ID."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            await _dme_request(
                client,
                "DELETE",
                f"/dns/managed/{provider_zone_id}/records/{provider_record_id}/",
                self.__api_key,
                self.__secret_key,
            )

    async def ensure_zone(self, zone_name: str) -> ZoneMeta:
        """
        Ensure the zone exists in DNSMadeEasy.
        First tries to find the zone in the existing managed domains list.
        If not found, attempts to create it.
        """
        zones = await self.list_zones(name_filter=zone_name)
        if zones:
            return zones[0]

        # Create the zone
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _dme_request(
                client,
                "POST",
                "/dns/managed/",
                self.__api_key,
                self.__secret_key,
                json={"name": zone_name.lower().strip(".")},
            )

        if isinstance(data, dict) and "id" in data:
            return _parse_dme_zone(data)

        # Re-fetch to get the zone
        zones = await self.list_zones(name_filter=zone_name)
        if zones:
            return zones[0]

        raise RuntimeError(
            f"Zone '{zone_name}' could not be created in DNSMadeEasy. "
            "Check API permissions and account limits."
        )
