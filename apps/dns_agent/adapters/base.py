"""
Abstract base class for DNS provider adapters.
All providers implement this interface — enables easy swap/extension.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ZoneMeta:
    provider_zone_id: str
    zone_name: str
    status: str = "active"


@dataclass
class RecordMeta:
    provider_record_id: str
    record_type: str
    name: str
    value: str
    ttl: int
    priority: int | None = None


@dataclass
class RecordSpec:
    record_type: str
    name: str
    value: str
    ttl: int = 300
    priority: int | None = None


class DnsProviderAdapter(ABC):
    """
    Interface for DNS provider adapters.
    All credential fetching is done during __init__ or explicit initialize() call.
    No tokens are stored as plain class attributes visible in logs.
    """

    @abstractmethod
    async def list_zones(self, name_filter: str | None = None) -> list[ZoneMeta]:
        """List zones available to the authenticated token."""
        ...

    @abstractmethod
    async def list_records(self, provider_zone_id: str) -> list[RecordMeta]:
        """List all records for a zone by provider zone ID."""
        ...

    @abstractmethod
    async def upsert_record(self, provider_zone_id: str, spec: RecordSpec) -> RecordMeta:
        """
        Create or update a record. Must be idempotent.
        Returns the provider's record metadata including provider_record_id.
        """
        ...

    @abstractmethod
    async def delete_record(self, provider_zone_id: str, provider_record_id: str) -> None:
        """Delete a record by its provider record ID."""
        ...

    @abstractmethod
    async def ensure_zone(self, zone_name: str) -> ZoneMeta:
        """
        Ensure a zone exists in the provider. Create it if missing.
        Returns zone metadata including provider_zone_id.
        """
        ...

    @abstractmethod
    async def find_record(
        self, provider_zone_id: str, record_type: str, name: str
    ) -> RecordMeta | None:
        """Find a specific record by type and name. Returns None if not found."""
        ...
