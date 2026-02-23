"""
Mock carrier adapter — preserves existing fixture behavior for local dev/testing.
Loads data from apps/carrier_agent/fixtures/mock_provider.json.
"""

from __future__ import annotations

import json
import os

from apps.carrier_agent.adapters.base import (
    AccountStatus,
    CarrierProviderAdapter,
    CnamStatus,
    DidRecord,
    MessagingStatus,
    TrunkRecord,
)

_FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "mock_provider.json"
)


def _load_fixture() -> dict:
    with open(_FIXTURE_PATH) as f:
        return json.load(f)


class MockCarrierAdapter(CarrierProviderAdapter):
    """Mock adapter — loads fixture data. Used when CARRIER_MOCK=true or provider='mock'."""

    def __repr__(self) -> str:
        return "MockCarrierAdapter()"

    async def get_account_status(self) -> AccountStatus:
        data = _load_fixture()
        return AccountStatus(
            provider="mock",
            status="active",
            balance=150.00,
            friendly_name=data.get("name", "Mock Provider"),
        )

    async def list_dids(self) -> list[DidRecord]:
        data = _load_fixture()
        return [
            DidRecord(
                number=d["number"],
                region=d.get("region"),
                voice_enabled=d.get("voice_enabled", True),
                sms_enabled=d.get("sms_enabled", False),
                e911_status=d.get("e911_status"),
                assigned_to=d.get("assigned_to"),
                tags=d.get("tags", []),
            )
            for d in data.get("dids", [])
        ]

    async def get_did(self, number: str) -> DidRecord | None:
        data = _load_fixture()
        did_data = next((d for d in data.get("dids", []) if d["number"] == number), None)
        if not did_data:
            return None
        return DidRecord(
            number=did_data["number"],
            region=did_data.get("region"),
            voice_enabled=did_data.get("voice_enabled", True),
            sms_enabled=did_data.get("sms_enabled", False),
            tags=did_data.get("tags", []),
        )

    async def list_trunks(self) -> list[TrunkRecord]:
        data = _load_fixture()
        return [
            TrunkRecord(
                trunk_id=t["trunk_id"], status=t.get("status", "active"), tags=t.get("tags", [])
            )
            for t in data.get("trunks", [])
        ]

    async def get_messaging_status(self) -> MessagingStatus:
        data = _load_fixture()
        ms = data.get("messaging_status", {})
        return MessagingStatus(overall_status=ms.get("status", "enabled"))

    async def get_cnam_status(self, number: str | None = None) -> CnamStatus:
        data = _load_fixture()
        cn = data.get("cnam_status", {})
        return CnamStatus(
            registered=cn.get("registered", False),
            display_name=cn.get("display_name"),
            status=cn.get("status", "unknown"),
        )

    async def purchase_did(self, number: str, capabilities: dict) -> DidRecord:
        return DidRecord(
            number=number,
            region="Mock Region",
            country_code="US",
            voice_enabled=capabilities.get("voice", True),
            sms_enabled=capabilities.get("sms", False),
            mms_enabled=capabilities.get("mms", False),
            provider_sid=f"PNmock{number.strip('+')}",
        )

    async def release_did(self, number: str, provider_sid: str | None = None) -> bool:
        return True

    async def create_or_update_trunk(
        self, trunk_id: str, friendly_name: str, termination_sip_domain: str | None = None
    ) -> TrunkRecord:
        return TrunkRecord(
            trunk_id=trunk_id if trunk_id and trunk_id != "new" else "TKmock123",
            friendly_name=friendly_name,
            status="active",
            termination_sip_domain=termination_sip_domain,
        )
