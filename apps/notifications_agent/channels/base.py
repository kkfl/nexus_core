"""
Abstract base for notification channel adapters.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SendResult:
    success: bool
    provider_msg_id: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None   # will be redacted before storage
    destination_hash: str = ""


class NotificationChannel(ABC):
    channel_name: str = "base"

    @abstractmethod
    async def send(self, *, subject: Optional[str], body: str,
                   destination: Optional[str] = None,
                   context: dict | None = None) -> SendResult:
        """
        Send the notification.
        `destination` is the channel-specific target: email, phone, chat_id, webhook URL.
        If None, the channel uses its configured default.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
