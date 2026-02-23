"""
Telegram notification channel — PRIMARY owner alert channel.

Bot API: POST https://api.telegram.org/bot<token>/sendMessage
Secrets (from vault):
  telegram.bot_token           — Bot API token
  telegram.default_chat_id    — Default chat ID (owner/admin)
  telegram.chat_ids.<group>   — Per-group chat IDs (optional)

INVARIANT: bot_token NEVER logged, never in error messages.
"""

from __future__ import annotations

import asyncio
import random
import re

import httpx
import structlog

from apps.notifications_agent.channels.base import NotificationChannel, SendResult

logger = structlog.get_logger(__name__)

_TG_MAX_LEN = 4096
_MAX_RETRIES = 3
_BASE_DELAY = 0.5


# ---------------------------------------------------------------------------
# Telegram MarkdownV2 escaping
# ---------------------------------------------------------------------------
_MD_SPECIAL = r"\_*[]()~`>#+-=|{}.!"


def escape_markdown_v2(text: str) -> str:
    """Escape all MarkdownV2 special characters except intentional formatting."""
    return re.sub(r"([" + re.escape(_MD_SPECIAL) + r"])", r"\\\1", text)


def _truncate(text: str, max_len: int = _TG_MAX_LEN) -> str:
    if len(text) <= max_len:
        return text
    suffix = "\n…\\[truncated\\]"
    return text[: max_len - len(suffix)] + suffix


# ---------------------------------------------------------------------------
# HTTP helper with retry
# ---------------------------------------------------------------------------


async def _tg_post(token: str, method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", _BASE_DELAY * (2**attempt)))
                wait += random.uniform(0, 0.3)
                logger.warning("telegram_rate_limited", attempt=attempt, wait_s=round(wait, 2))
                await asyncio.sleep(wait)
                continue
            data = resp.json()
            if not data.get("ok"):
                err = data.get("description", "unknown")
                code = str(data.get("error_code", ""))
                # SAFE to log description — it never contains the token
                raise RuntimeError(f"Telegram API error {code}: {err}")
            return data
        except httpx.TimeoutException as exc:
            delay = _BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 0.2)
            logger.warning("telegram_timeout", attempt=attempt, retry_in=round(delay, 2))
            last_exc = exc
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(delay)
    raise RuntimeError(f"Telegram request failed after {_MAX_RETRIES} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Channel implementation
# ---------------------------------------------------------------------------


class TelegramChannel(NotificationChannel):
    """
    Full Telegram implementation.
    token and default_chat_id are private — never in repr/logs.
    """

    channel_name = "telegram"

    def __init__(self, token: str, default_chat_id: str, parse_mode: str = "MarkdownV2") -> None:
        self.__token = token
        self.__default_chat_id = default_chat_id
        self._parse_mode = parse_mode

    def __repr__(self) -> str:
        return "TelegramChannel(token=[REDACTED], chat_id=[REDACTED])"

    async def send(
        self,
        *,
        subject: str | None,
        body: str,
        destination: str | None = None,
        context: dict | None = None,
    ) -> SendResult:
        chat_id = destination or self.__default_chat_id
        if not chat_id:
            return SendResult(
                success=False, error_code="no_destination", error_detail="No chat_id configured"
            )

        # Build message: bold subject + body
        parts = []
        if subject:
            parts.append(f"*{escape_markdown_v2(subject)}*")
        parts.append(escape_markdown_v2(body))
        message = "\n\n".join(parts)
        message = _truncate(message)

        # Optional thread support via context
        payload: dict = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": self._parse_mode,
        }
        if context and (thread_id := context.get("message_thread_id")):
            payload["message_thread_id"] = int(thread_id)

        try:
            data = await _tg_post(self.__token, "sendMessage", payload)
            msg_id = str(data.get("result", {}).get("message_id", ""))
            logger.info("telegram_sent", chat_id_hash=_hash_dest(chat_id), msg_id=msg_id)
            from apps.notifications_agent.audit.log import hash_destination

            return SendResult(
                success=True,
                provider_msg_id=msg_id,
                destination_hash=hash_destination(chat_id),
            )
        except Exception as exc:
            safe = str(exc)  # Telegram descriptions are safe; token not in exception
            logger.error("telegram_send_failed", error=safe)
            from apps.notifications_agent.audit.log import hash_destination

            return SendResult(
                success=False,
                destination_hash=hash_destination(chat_id),
                error_code="telegram_error",
                error_detail=safe[:500],
            )


def _hash_dest(dest: str) -> str:
    import hashlib

    return hashlib.sha256(dest.encode()).hexdigest()[:12]
