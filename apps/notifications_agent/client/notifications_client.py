"""
Thin client library for notifications_agent.
Used by nexus_api and other agents to send notifications.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


class NotificationsClient:
    """
    Call notifications_agent's POST /v1/notify.
    Handles connection errors gracefully — notifications must never block orchestrator flows.
    """

    def __init__(self, base_url: str, service_id: str, api_key: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_id = service_id
        self.__api_key = api_key  # private — never logged
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"NotificationsClient(base_url={self._base_url}, service_id={self._service_id})"

    def _headers(self) -> dict:
        return {
            "X-Service-ID": self._service_id,
            "X-Agent-Key": self.__api_key,
        }

    async def notify(
        self,
        *,
        tenant_id: str,
        env: str = "prod",
        severity: str,
        template_id: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        context: dict[str, Any] | None = None,
        channels: list[str] | None = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        sensitivity: str = "normal",
        destinations: dict[str, str] | None = None,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        """
        Send a notification request. Non-blocking — returns job metadata.
        If notifications_agent is unavailable, logs warning and returns error dict
        (does not raise by default, so orchestrator flows are never blocked).
        """
        idem_key = idempotency_key or str(uuid.uuid4())
        corr_id = correlation_id or str(uuid.uuid4())

        payload = {
            "tenant_id": tenant_id,
            "env": env,
            "severity": severity,
            "idempotency_key": idem_key,
            "correlation_id": corr_id,
            "sensitivity": sensitivity,
        }
        if template_id:
            payload["template_id"] = template_id
        if subject:
            payload["subject"] = subject
        if body:
            payload["body"] = body
        if context:
            payload["context"] = context
        if channels:
            payload["channels"] = channels
        if destinations:
            payload["destinations"] = destinations

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/notify",
                    json=payload,
                    headers=self._headers(),
                )
            if resp.status_code == 202:
                return resp.json()
            logger.warning(
                "notifications_client_error", status=resp.status_code, body=resp.text[:200]
            )
            result = {"error": f"HTTP {resp.status_code}", "detail": resp.text[:200]}
            if raise_on_error:
                raise RuntimeError(result["error"])
            return result
        except httpx.TimeoutException:
            logger.warning("notifications_client_timeout", url=self._base_url)
            if raise_on_error:
                raise
            return {"error": "timeout", "detail": "notifications-agent did not respond in time"}
        except Exception as exc:
            logger.warning("notifications_client_failed", error=str(exc)[:200])
            if raise_on_error:
                raise
            return {"error": "unavailable", "detail": str(exc)[:200]}

    async def notify_agent_down(
        self,
        agent: str,
        reason: str,
        *,
        tenant_id: str,
        env: str = "prod",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.notify(
            tenant_id=tenant_id,
            env=env,
            severity="critical",
            template_id="agent_down",
            context={"agent": agent, "reason": reason},
            idempotency_key=f"agent_down:{agent}:{env}:{correlation_id or uuid.uuid4()}",
            correlation_id=correlation_id,
        )

    async def notify_job_failed(
        self,
        job_id: str,
        service: str,
        error: str,
        *,
        tenant_id: str,
        env: str = "prod",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.notify(
            tenant_id=tenant_id,
            env=env,
            severity="error",
            template_id="job_failed",
            context={"job_id": job_id, "service": service, "error": error},
            idempotency_key=f"job_failed:{job_id}:{correlation_id or uuid.uuid4()}",
            correlation_id=correlation_id,
        )
