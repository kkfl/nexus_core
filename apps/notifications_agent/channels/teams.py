"""MS Teams channel — STUB. V2 implementation."""
from apps.notifications_agent.channels.base import NotificationChannel, SendResult
from typing import Optional


class TeamsChannel(NotificationChannel):
    channel_name = "teams"

    async def send(self, *, subject: Optional[str], body: str,
                   destination: Optional[str] = None,
                   context: dict | None = None) -> SendResult:
        return SendResult(success=False, error_code="not_implemented",
                          error_detail="Teams channel not implemented in V1", destination_hash="")
