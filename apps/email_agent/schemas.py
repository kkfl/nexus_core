"""
email_agent — Pydantic request/response schemas.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ── Send ──────────────────────────────────────────────────────────────────────


class TestSendRequest(BaseModel):
    to: str
    subject: str = "Nexus Test Email"
    body_text: str = "This is a test email from Nexus."


class SendRequest(BaseModel):
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body_text: str
    body_html: str | None = None


class SendResponse(BaseModel):
    ok: bool
    message_id: str | None = None
    error: str | None = None


# ── Inbox / Messages ─────────────────────────────────────────────────────────


class MessageSummary(BaseModel):
    id: str
    message_id: str | None = None
    from_addr: str | None = None
    to_addr: str | None = None
    subject: str | None = None
    date: datetime | None = None
    flags: str | None = None
    attachment_count: int = 0


class MessageDetail(MessageSummary):
    cc_addr: str | None = None
    body_text: str | None = None
    body_html: str | None = None


class AttachmentMeta(BaseModel):
    id: str
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None


# ── Admin ─────────────────────────────────────────────────────────────────────


class MailboxInfo(BaseModel):
    email: str
    domain: str
    active: int
    quota: int = 0
    created: str | None = None


class MailboxStats(BaseModel):
    """Per-mailbox quota + activity stats."""

    email: str
    quota_mb: int = 0
    used_mb: float = 0
    used_pct: float = 0
    free_mb: float = 0
    free_pct: float = 100
    unread_count: int = 0
    total_count: int = 0
    last_received_at: str | None = None


class MailboxWithStats(MailboxInfo):
    """MailboxInfo extended with stats from doveadm."""

    used_mb: float = 0
    used_pct: float = 0
    free_pct: float = 100
    unread_count: int = 0
    total_count: int = 0
    last_received_at: str | None = None
    readable: bool = False


class MessageListItem(BaseModel):
    """Message summary for inbox listing."""

    uid: str
    subject: str = ""
    from_addr: str = ""
    to_addr: str = ""
    date: str = ""
    flags: list[str] = Field(default_factory=list)
    has_attachments: bool = False
    size_bytes: int = 0
    is_read: bool = False


class MessageFull(MessageListItem):
    """Full message with body and attachment metadata."""

    cc_addr: str = ""
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[AttachmentMeta] = Field(default_factory=list)


class CreateMailboxRequest(BaseModel):
    email: str
    password: str


class SetPasswordRequest(BaseModel):
    email: str
    password: str


class DisableMailboxRequest(BaseModel):
    email: str


class AddAliasRequest(BaseModel):
    alias: str
    destination: str


class AdminResponse(BaseModel):
    ok: bool
    email: str | None = None
    alias: str | None = None
    destination: str | None = None
    action: str | None = None
    error: str | None = None


# ── Server Stats ─────────────────────────────────────────────────────────────


class ServerStats(BaseModel):
    """Postfix server-level queue stats."""

    queue_total: int = 0
    deferred: int = 0
    active: int = 0
    hold: int = 0
    corrupt: int = 0


# ── Health ────────────────────────────────────────────────────────────────────


class HealthStatus(BaseModel):
    smtp: str  # "ok" | "error"
    imap: str  # "ok" | "error"
    ssh_bridge: str  # "ok" | "error"
    smtp_detail: str | None = None
    imap_detail: str | None = None
    ssh_detail: str | None = None
