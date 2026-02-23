"""
Abstract base for notification channel adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SendResult:
    success: bool
    provider_msg_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None  # will be redacted before storage
    destination_hash: str = ""


class NotificationChannel(ABC):
    channel_name: str = "base"

    @abstractmethod
    async def send(
        self,
        *,
        subject: str | None,
        body: str,
        destination: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        """
        Send the notification.
        `destination` is the channel-specific target: email, phone, chat_id, webhook URL.
        If None, the channel uses its configured default.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
