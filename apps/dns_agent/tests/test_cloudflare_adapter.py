"""
Unit tests for the Cloudflare DNS adapter.
Uses httpx mocking to avoid real Cloudflare API calls.
"""
from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from apps.dns_agent.adapters.cloudflare import CloudflareAdapter
from apps.dns_agent.adapters.base import RecordSpec


def _mock_cf_response(payload: dict) -> httpx.Response:
    import json
    return httpx.Response(
        200,
        content=json.dumps({"success": True, "result": payload, "errors": [], "messages": []}),
        headers={"Content-Type": "application/json"},
    )


@pytest.fixture
def adapter():
    return CloudflareAdapter(api_token="test-token-redacted")


def test_adapter_repr_redacts_token(adapter):
    """Token must NEVER appear in repr()."""
    r = repr(adapter)
    assert "test-token-redacted" not in r
    assert "[REDACTED]" in r


@pytest.mark.asyncio
async def test_list_zones(adapter):
    zone_data = [{"id": "zone-abc", "name": "example.com", "status": "active"}]
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_cf_response(zone_data)
        zones = await adapter.list_zones()
    assert len(zones) == 1
    assert zones[0].zone_name == "example.com"
    assert zones[0].provider_zone_id == "zone-abc"


@pytest.mark.asyncio
async def test_list_records(adapter):
    records_data = [
        {"id": "rec-1", "type": "A", "name": "api.example.com", "content": "1.2.3.4", "ttl": 300},
        {"id": "rec-2", "type": "MX", "name": "example.com", "content": "mail.example.com",
         "ttl": 300, "priority": 10},
    ]
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = _mock_cf_response(records_data)
        records = await adapter.list_records("zone-abc")
    assert len(records) == 2
    assert records[0].record_type == "A"
    assert records[0].value == "1.2.3.4"
    assert records[1].priority == 10


@pytest.mark.asyncio
async def test_upsert_creates_when_not_exists(adapter):
    """Upsert should create a new record when it doesn't already exist."""
    empty_find = httpx.Response(
        200,
        content='{"success":true,"result":[],"errors":[],"messages":[]}',
        headers={"Content-Type": "application/json"},
    )
    created = {"id": "rec-new", "type": "A", "name": "api", "content": "5.6.7.8", "ttl": 300}

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = [empty_find, _mock_cf_response(created)]
        spec = RecordSpec(record_type="A", name="api", value="5.6.7.8", ttl=300)
        result = await adapter.upsert_record("zone-abc", spec)

    assert result.provider_record_id == "rec-new"
    assert result.value == "5.6.7.8"
    # Second call should be POST (create), not PATCH
    calls = mock_req.call_args_list
    assert calls[1][0][0] == "POST"


@pytest.mark.asyncio
async def test_upsert_patches_when_exists(adapter):
    """Upsert should PATCH an existing record."""
    existing = {"id": "rec-existing", "type": "A", "name": "api", "content": "1.2.3.4", "ttl": 300}
    updated = {"id": "rec-existing", "type": "A", "name": "api", "content": "5.6.7.8", "ttl": 300}

    find_resp = httpx.Response(
        200,
        content=f'{{"success":true,"result":[{{"id":"rec-existing","type":"A","name":"api","content":"1.2.3.4","ttl":300}}],"errors":[],"messages":[]}}',
        headers={"Content-Type": "application/json"},
    )

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = [find_resp, _mock_cf_response(updated)]
        spec = RecordSpec(record_type="A", name="api", value="5.6.7.8", ttl=300)
        result = await adapter.upsert_record("zone-abc", spec)

    assert result.value == "5.6.7.8"
    calls = mock_req.call_args_list
    assert calls[1][0][0] == "PATCH"


@pytest.mark.asyncio
async def test_rate_limit_retries(adapter):
    """429 response should trigger backoff and retry."""
    import json
    rate_limit = httpx.Response(
        429,
        content='{"success":false,"errors":[]}',
        headers={"Retry-After": "0.1", "Content-Type": "application/json"},
    )
    success = _mock_cf_response([{"id": "z1", "name": "example.com", "status": "active"}])

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = [rate_limit, success]
        with patch("asyncio.sleep", new_callable=AsyncMock):  # Speed up test
            zones = await adapter.list_zones()

    assert len(zones) == 1


@pytest.mark.asyncio
async def test_token_not_in_error_messages(adapter):
    """Error messages from Cloudflare must not include auth tokens."""
    error_resp = httpx.Response(
        200,
        content='{"success":false,"errors":[{"code":9103,"message":"Invalid access token"}],"result":null}',
        headers={"Content-Type": "application/json"},
    )
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = error_resp
        with pytest.raises(RuntimeError) as exc_info:
            await adapter.list_zones()
    # The token "test-token-redacted" must not appear in the error
    assert "test-token-redacted" not in str(exc_info.value)
