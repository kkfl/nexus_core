"""
Channel factory — fetches credentials from vault at runtime and builds channel.
NEVER caches credentials across requests.
"""

from __future__ import annotations

import structlog

from apps.notifications_agent.channels.base import NotificationChannel
from apps.notifications_agent.channels.slack import SlackChannel
from apps.notifications_agent.channels.sms import SmsChannel, SmsChannelNotConfigured
from apps.notifications_agent.channels.smtp import SmtpChannel
from apps.notifications_agent.channels.teams import TeamsChannel
from apps.notifications_agent.channels.telegram import TelegramChannel
from apps.notifications_agent.channels.webhook import WebhookChannel
from apps.secrets_agent.client.vault_client import VaultClient, VaultError

logger = structlog.get_logger(__name__)


async def build_channel(
    channel_name: str,
    vault: VaultClient,
    tenant_id: str = "nexus",
    env: str = "prod",
    correlation_id: str | None = None,
    channel_config: dict | None = None,
) -> NotificationChannel:
    """
    Build the channel adapter, fetching credentials from vault.
    channel_config: non-secret runtime config (webhook_url, chat_id overrides, etc.)
    """
    cfg = channel_config or {}

    if channel_name == "telegram":
        token = await vault.get_secret(
            alias="telegram.bot_token",
            tenant_id=tenant_id,
            env=env,
            reason="notifications_telegram_send",
            correlation_id=correlation_id,
        )
        chat_id = cfg.get("chat_id") or await vault.get_secret(
            alias="telegram.default_chat_id",
            tenant_id=tenant_id,
            env=env,
            reason="notifications_telegram_send",
            correlation_id=correlation_id,
        )
        return TelegramChannel(token=token, default_chat_id=chat_id)

    elif channel_name == "email":
        host = await vault.get_secret(
            alias="smtp.host",
            tenant_id=tenant_id,
            env=env,
            reason="notifications_smtp",
            correlation_id=correlation_id,
        )
        port_str = await vault.get_secret(
            alias="smtp.port",
            tenant_id=tenant_id,
            env=env,
            reason="notifications_smtp",
            correlation_id=correlation_id,
        )
        username = await vault.get_secret(
            alias="smtp.username",
            tenant_id=tenant_id,
            env=env,
            reason="notifications_smtp",
            correlation_id=correlation_id,
        )
        password = await vault.get_secret(
            alias="smtp.password",
            tenant_id=tenant_id,
            env=env,
            reason="notifications_smtp",
            correlation_id=correlation_id,
        )
        from_addr = await vault.get_secret(
            alias="smtp.from_address",
            tenant_id=tenant_id,
            env=env,
            reason="notifications_smtp",
            correlation_id=correlation_id,
        )
        port = int(port_str)
        return SmtpChannel(
            host=host,
            port=port,
            username=username,
            password=password,
            from_address=from_addr,
            use_tls=(port == 465),  # 465=implicit TLS, 587=STARTTLS
        )

    elif channel_name == "sms":
        try:
            sid = await vault.get_secret(
                alias="sms.twilio.account_sid",
                tenant_id=tenant_id,
                env=env,
                reason="notifications_sms",
                correlation_id=correlation_id,
            )
            tok = await vault.get_secret(
                alias="sms.twilio.auth_token",
                tenant_id=tenant_id,
                env=env,
                reason="notifications_sms",
                correlation_id=correlation_id,
            )
            frm = await vault.get_secret(
                alias="sms.twilio.from_number",
                tenant_id=tenant_id,
                env=env,
                reason="notifications_sms",
                correlation_id=correlation_id,
            )
            return SmsChannel(account_sid=sid, auth_token=tok, from_number=frm)
        except VaultError:
            logger.warning("sms_vault_aliases_not_found", tenant_id=tenant_id)
            return SmsChannelNotConfigured()

    elif channel_name == "webhook":
        signing_secret = await vault.get_secret(
            alias=f"webhook.{tenant_id}.signing_secret",
            tenant_id=tenant_id,
            env=env,
            reason="notifications_webhook",
            correlation_id=correlation_id,
        )
        return WebhookChannel(signing_secret=signing_secret)

    elif channel_name == "slack":
        return SlackChannel()

    elif channel_name == "teams":
        return TeamsChannel()

    else:
        raise ValueError(f"Unknown channel: '{channel_name}'")
