"""
Unit tests for the Twilio carrier adapter.
Mocks HTTP — no real Twilio API calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from apps.carrier_agent.adapters.twilio import TwilioAdapter


def _mock_resp(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture
def adapter():
    return TwilioAdapter(account_sid="AC_TEST_SID", auth_token="TEST_AUTH_TOKEN_REDACTED")


def test_adapter_repr_redacts_credentials(adapter):
    """Credentials must NEVER appear in repr()."""
    r = repr(adapter)
    assert "AC_TEST_SID" not in r
    assert "TEST_AUTH_TOKEN_REDACTED" not in r
    assert "[REDACTED]" in r


@pytest.mark.asyncio
async def test_get_account_status(adapter):
    payload = {
        "sid": "AC_TEST_SID",
        "status": "active",
        "friendly_name": "Test Account",
        "date_created": "2023-01-01",
    }
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_resp(payload)
        status = await adapter.get_account_status()
    assert status.status == "active"
    assert status.friendly_name == "Test Account"
    assert status.provider == "twilio"


@pytest.mark.asyncio
async def test_list_dids(adapter):
    payload = {
        "incoming_phone_numbers": [
            {
                "sid": "PN123",
                "phone_number": "+15005550001",
                "iso_country": "US",
                "region": "CA",
                "capabilities": {"voice": True, "SMS": True, "MMS": False},
                "voice_application_sid": None,
            },
        ]
    }
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_resp(payload)
        dids = await adapter.list_dids()
    assert len(dids) == 1
    assert dids[0].number == "+15005550001"
    assert dids[0].voice_enabled is True
    assert dids[0].sms_enabled is True
    assert dids[0].mms_enabled is False
    assert dids[0].provider_sid == "PN123"


@pytest.mark.asyncio
async def test_get_did_not_found(adapter):
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_resp({"incoming_phone_numbers": []})
        result = await adapter.get_did("+19999999999")
    assert result is None


@pytest.mark.asyncio
async def test_list_trunks(adapter):
    payload = {
        "trunks": [
            {
                "sid": "TK123",
                "friendly_name": "Main Trunk",
                "domain_name": "mytrunk.pstn.twilio.com",
            },
        ]
    }
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_resp(payload)
        trunks = await adapter.list_trunks()
    assert len(trunks) == 1
    assert trunks[0].trunk_id == "TK123"
    assert trunks[0].termination_sip_domain == "mytrunk.pstn.twilio.com"


@pytest.mark.asyncio
async def test_rate_limit_retry(adapter):
    """429 should trigger backoff and retry."""
    rate_limit = httpx.Response(
        429,
        content=b'{"error":"too many requests"}',
        headers={"Retry-After": "0.1", "Content-Type": "application/json"},
    )
    success = _mock_resp({"incoming_phone_numbers": []})
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = [rate_limit, success]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            dids = await adapter.list_dids()
    assert dids == []
    assert mock_req.call_count == 2


@pytest.mark.asyncio
async def test_credentials_not_in_error_message(adapter):
    """Twilio error body must not include the auth token."""
    error_resp = _mock_resp(
        {"code": 20003, "message": "Authentication failure", "status": 401},
        status=401,
    )
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = error_resp
        with pytest.raises(RuntimeError) as exc_info:
            await adapter.list_dids()
    assert "TEST_AUTH_TOKEN_REDACTED" not in str(exc_info.value)
    assert "AC_TEST_SID" not in str(exc_info.value)
