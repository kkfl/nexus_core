"""
DNSMadeEasy adapter — STUB.

TODO V2: Implement full DNSMadeEasy adapter.
  API docs: https://dnsmadeeasy.com/integration/

  Auth uses HMAC-SHA1 signing with:
    - api_key:    alias dns.dnsmadeeasy.api_key    (from secrets_agent)
    - secret_key: alias dns.dnsmadeeasy.secret_key (from secrets_agent)

  Each request requires:
    - X-Dnsme-Apikey header (api_key)
    - X-Dnsme-Requestdate header (RFC 1123 datetime)
    - X-Dnsme-Hmac header (HMAC-SHA1 of requestdate with secret_key)

See: https://api.dnsmadeeasy.com/V2.0/ for endpoint reference.
"""

from __future__ import annotations

from apps.dns_agent.adapters.base import DnsProviderAdapter, RecordMeta, RecordSpec, ZoneMeta


class DNSMadeEasyAdapter(DnsProviderAdapter):
    """Stub adapter for DNSMadeEasy. All methods raise NotImplementedError."""

    def __init__(self, api_key: str, secret_key: str) -> None:
        self.__api_key = api_key
        self.__secret_key = secret_key

    def __repr__(self) -> str:
        return "DNSMadeEasyAdapter(credentials=[REDACTED])"

    async def list_zones(self, name_filter: str | None = None) -> list[ZoneMeta]:
        raise NotImplementedError(
            "DNSMadeEasy adapter is a TODO stub — see adapters/dnsmadeeasy.py"
        )

    async def list_records(self, provider_zone_id: str) -> list[RecordMeta]:
        raise NotImplementedError(
            "DNSMadeEasy adapter is a TODO stub — see adapters/dnsmadeeasy.py"
        )

    async def find_record(
        self, provider_zone_id: str, record_type: str, name: str
    ) -> RecordMeta | None:
        raise NotImplementedError(
            "DNSMadeEasy adapter is a TODO stub — see adapters/dnsmadeeasy.py"
        )

    async def upsert_record(self, provider_zone_id: str, spec: RecordSpec) -> RecordMeta:
        raise NotImplementedError(
            "DNSMadeEasy adapter is a TODO stub — see adapters/dnsmadeeasy.py"
        )

    async def delete_record(self, provider_zone_id: str, provider_record_id: str) -> None:
        raise NotImplementedError(
            "DNSMadeEasy adapter is a TODO stub — see adapters/dnsmadeeasy.py"
        )

    async def ensure_zone(self, zone_name: str) -> ZoneMeta:
        raise NotImplementedError(
            "DNSMadeEasy adapter is a TODO stub — see adapters/dnsmadeeasy.py"
        )
