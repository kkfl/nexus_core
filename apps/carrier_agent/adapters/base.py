"""
Abstract base for carrier provider adapters.
All providers implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AccountStatus:
    provider: str
    status: str  # active | suspended | closed
    balance: float | None = None
    currency: str = "USD"
    friendly_name: str = ""


@dataclass
class DidRecord:
    number: str
    region: str | None = None
    country_code: str = "US"
    voice_enabled: bool = True
    sms_enabled: bool = False
    mms_enabled: bool = False
    e911_status: str | None = None
    assigned_to: str | None = None
    tags: list[str] = field(default_factory=list)
    provider_sid: str | None = None  # provider's internal ID


@dataclass
class TrunkRecord:
    trunk_id: str
    friendly_name: str = ""
    status: str = "active"
    origination_url: str | None = None
    termination_sip_domain: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class MessagingStatus:
    overall_status: str  # enabled | disabled
    monthly_sent: int | None = None
    monthly_received: int | None = None


@dataclass
class CnamStatus:
    registered: bool = False
    display_name: str | None = None
    status: str = "unknown"


class CarrierProviderAdapter(ABC):
    """Interface all carrier adapters must implement."""

    @abstractmethod
    async def get_account_status(self) -> AccountStatus: ...

    @abstractmethod
    async def list_dids(self) -> list[DidRecord]: ...

    @abstractmethod
    async def get_did(self, number: str) -> DidRecord | None: ...

    @abstractmethod
    async def list_trunks(self) -> list[TrunkRecord]: ...

    @abstractmethod
    async def get_messaging_status(self) -> MessagingStatus: ...

    @abstractmethod
    async def get_cnam_status(self, number: str | None = None) -> CnamStatus: ...

    @abstractmethod
    async def purchase_did(self, number: str, capabilities: dict) -> DidRecord:
        """Purchase a specific DID. capabilities = {'voice': True, 'sms': False, 'mms': False}"""
        ...

    @abstractmethod
    async def release_did(self, number: str, provider_sid: str | None = None) -> bool:
        """Release a DID back to the provider."""
        ...

    @abstractmethod
    async def create_or_update_trunk(
        self, trunk_id: str, friendly_name: str, termination_sip_domain: str | None = None
    ) -> TrunkRecord:
        """Create or update a SIP trunk configuration."""
        ...
