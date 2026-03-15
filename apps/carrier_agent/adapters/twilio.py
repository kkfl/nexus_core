"""
Twilio Carrier Adapter — Full V1 implementation.

Uses Twilio REST API v2010: https://www.twilio.com/docs/phone-numbers/api

Auth: HTTP Basic Auth — Account SID + Auth Token
  Fetched from secrets_agent at runtime by alias:
    carrier.<target_id>.account_sid   — Twilio Account SID (ACxxxxxx…)
    carrier.<target_id>.auth_token    — Twilio Auth Token

INVARIANT: Auth token is NEVER logged in any function in this module.
"""

from __future__ import annotations

import asyncio
import random
import re

import httpx
import structlog

from apps.carrier_agent.adapters.base import (
    AccountStatus,
    CarrierProviderAdapter,
    CnamStatus,
    DidRecord,
    MessagingStatus,
    TrunkRecord,
)

logger = structlog.get_logger(__name__)

_TWILIO_BASE = "https://api.twilio.com/2010-04-01"
_MAX_RETRIES = 3
_BASE_DELAY = 0.5


async def _twilio_request(
    client: httpx.AsyncClient, method: str, url: str, account_sid: str, auth_token: str, **kwargs
) -> dict:
    """
    Perform a Twilio API request with retry + backoff.
    Auth credentials are passed as Basic auth — never logged.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = await client.request(
                method,
                url,
                auth=(account_sid, auth_token),
                **kwargs,
            )
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", _BASE_DELAY * (2**attempt)))
                wait += random.uniform(0, 0.3)
                logger.warning(
                    "twilio_rate_limited", url=url, attempt=attempt, wait_s=round(wait, 2)
                )
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 500:
                delay = _BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                logger.warning("twilio_server_error", status=resp.status_code, attempt=attempt)
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(delay)
                    continue
            if resp.status_code == 404:
                return {}
            if resp.status_code >= 400:
                # Twilio errors include a message — safe to surface (no credentials in error body)
                body = resp.json() if resp.content else {}
                safe_url = re.sub(r"/Accounts/AC[A-Za-z0-9_]+", "/Accounts/[REDACTED]", url)
                raise RuntimeError(
                    f"Twilio {method} {safe_url} → {resp.status_code}: {body.get('message', resp.text[:200])}"
                )
            return resp.json() if resp.content else {}
        except httpx.TimeoutException as exc:
            delay = _BASE_DELAY * (2 ** (attempt - 1))
            logger.warning("twilio_timeout", attempt=attempt, retry_in=round(delay, 2))
            last_exc = exc
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(delay)
    raise RuntimeError(f"Twilio request failed after {_MAX_RETRIES} attempts: {last_exc}")


class TwilioAdapter(CarrierProviderAdapter):
    """
    Full Twilio adapter.
    Account SID and Auth Token are stored as private attributes.
    They NEVER appear in repr(), logs, or exception messages.
    """

    def __init__(self, account_sid: str, auth_token: str) -> None:
        self.__account_sid = account_sid
        self.__auth_token = auth_token
        self._timeout = httpx.Timeout(10.0)

    def __repr__(self) -> str:
        return "TwilioAdapter(account_sid=[REDACTED])"

    def _accounts_url(self, path: str = "") -> str:
        return f"{_TWILIO_BASE}/Accounts/{self.__account_sid}{path}.json"

    async def get_account_status(self) -> AccountStatus:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _twilio_request(
                client,
                "GET",
                self._accounts_url(),
                self.__account_sid,
                self.__auth_token,
            )
        return AccountStatus(
            provider="twilio",
            status=data.get("status", "unknown"),
            friendly_name=data.get("friendly_name", ""),
        )

    async def list_dids(self) -> list[DidRecord]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _twilio_request(
                client,
                "GET",
                self._accounts_url("/IncomingPhoneNumbers"),
                self.__account_sid,
                self.__auth_token,
                params={"PageSize": 1000},
            )
        numbers = data.get("incoming_phone_numbers", [])
        return [
            DidRecord(
                number=n.get("phone_number", ""),
                region=n.get("region"),
                country_code=n.get("iso_country", "US"),
                voice_enabled=n.get("capabilities", {}).get("voice", False),
                sms_enabled=n.get("capabilities", {}).get("SMS", False),
                mms_enabled=n.get("capabilities", {}).get("MMS", False),
                provider_sid=n.get("sid"),
                assigned_to=n.get("voice_application_sid"),
            )
            for n in numbers
        ]

    async def get_did(self, number: str) -> DidRecord | None:
        # Twilio accepts E.164 format in filter
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _twilio_request(
                client,
                "GET",
                self._accounts_url("/IncomingPhoneNumbers"),
                self.__account_sid,
                self.__auth_token,
                params={"PhoneNumber": number, "PageSize": 10},
            )
        numbers = data.get("incoming_phone_numbers", [])
        if not numbers:
            return None
        n = numbers[0]
        return DidRecord(
            number=n.get("phone_number", ""),
            region=n.get("region"),
            country_code=n.get("iso_country", "US"),
            voice_enabled=n.get("capabilities", {}).get("voice", False),
            sms_enabled=n.get("capabilities", {}).get("SMS", False),
            mms_enabled=n.get("capabilities", {}).get("MMS", False),
            provider_sid=n.get("sid"),
            assigned_to=n.get("voice_application_sid"),
        )

    async def list_trunks(self) -> list[TrunkRecord]:
        """List SIP elastic trunks via Twilio Trunking API."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _twilio_request(
                client,
                "GET",
                "https://trunking.twilio.com/v1/Trunks",
                self.__account_sid,
                self.__auth_token,
                params={"PageSize": 100},
            )
        trunks = data.get("trunks", [])
        return [
            TrunkRecord(
                trunk_id=t.get("sid", ""),
                friendly_name=t.get("friendly_name", ""),
                status="active",  # Twilio trunks don't have a discrete active/inactive status field
                termination_sip_domain=t.get("domain_name"),
            )
            for t in trunks
        ]

    async def get_messaging_status(self) -> MessagingStatus:
        """Return messaging capability status. Twilio doesn't have a single messaging-status endpoint,
        so we return a summary based on account state."""
        status = await self.get_account_status()
        return MessagingStatus(
            overall_status="enabled" if status.status == "active" else "disabled",
        )

    async def get_cnam_status(self, number: str | None = None) -> CnamStatus:
        """
        Check CNAM status for a DID. Twilio exposes caller ID as a resource.
        If number is None, checks the account's first number.
        """
        if number:
            did = await self.get_did(number)
            if did and did.provider_sid:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    data = await _twilio_request(
                        client,
                        "GET",
                        self._accounts_url(f"/IncomingPhoneNumbers/{did.provider_sid}"),
                        self.__account_sid,
                        self.__auth_token,
                    )
                friendly_name = data.get("friendly_name", "")
                return CnamStatus(
                    registered=bool(friendly_name),
                    display_name=friendly_name if friendly_name else None,
                    status="registered" if friendly_name else "not_registered",
                )
        return CnamStatus(status="unknown")

    async def purchase_did(self, number: str, capabilities: dict) -> DidRecord:
        """
        Purchase a specific phone number.
        Twilio requires the exact E.164 number in the PhoneNumber parameter.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await _twilio_request(
                client,
                "POST",
                self._accounts_url("/IncomingPhoneNumbers"),
                self.__account_sid,
                self.__auth_token,
                data={"PhoneNumber": number},
            )

        return DidRecord(
            number=data.get("phone_number", ""),
            region=data.get("region"),
            country_code=data.get("iso_country", "US"),
            voice_enabled=data.get("capabilities", {}).get("voice", False),
            sms_enabled=data.get("capabilities", {}).get("SMS", False),
            mms_enabled=data.get("capabilities", {}).get("MMS", False),
            provider_sid=data.get("sid"),
            assigned_to=data.get("voice_application_sid"),
        )

    async def release_did(self, number: str, provider_sid: str | None = None) -> bool:
        """
        Release a phone number back to Twilio.
        Requires the provider_sid (e.g. PNxxxxxxxx). If not provided, we look it up.
        """
        if not provider_sid:
            did = await self.get_did(number)
            if not did or not did.provider_sid:
                return False
            provider_sid = did.provider_sid

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                await _twilio_request(
                    client,
                    "DELETE",
                    self._accounts_url(f"/IncomingPhoneNumbers/{provider_sid}"),
                    self.__account_sid,
                    self.__auth_token,
                )
                return True
            except Exception as e:
                logger.error("twilio_release_failed", number=number, error=str(e))
                return False

    async def create_or_update_trunk(
        self, trunk_id: str, friendly_name: str, termination_sip_domain: str | None = None
    ) -> TrunkRecord:
        """
        Create or update a SIP trunk.
        If trunk_id is provided, we update it. If not, or if it says 'new', we create it.
        We also look up by friendly_name to see if it already exists to be idempotent.
        """
        target_sid = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # First, list trunks to see if one matches the ID or name
            if trunk_id and trunk_id != "new":
                target_sid = trunk_id
            else:
                trunks = await self.list_trunks()
                for trunk in trunks:
                    if trunk.friendly_name == friendly_name:
                        target_sid = trunk.trunk_id
                        break

            payload = {"FriendlyName": friendly_name}
            if termination_sip_domain:
                payload["DomainName"] = termination_sip_domain

            if target_sid:
                # Update existing
                data = await _twilio_request(
                    client,
                    "POST",
                    f"https://trunking.twilio.com/v1/Trunks/{target_sid}",
                    self.__account_sid,
                    self.__auth_token,
                    data=payload,
                )
            else:
                # Create new
                data = await _twilio_request(
                    client,
                    "POST",
                    "https://trunking.twilio.com/v1/Trunks",
                    self.__account_sid,
                    self.__auth_token,
                    data=payload,
                )

        return TrunkRecord(
            trunk_id=data.get("sid", ""),
            friendly_name=data.get("friendly_name", ""),
            status="active",
            termination_sip_domain=data.get("domain_name"),
        )
