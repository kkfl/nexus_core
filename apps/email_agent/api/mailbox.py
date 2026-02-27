"""
email_agent — mailbox drill-down endpoints (message reading).

Allowlist-gated: only configured mailboxes can be read.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from apps.email_agent.auth.identity import verify_service_identity
from apps.email_agent.config import config
from apps.email_agent.schemas import MessageListItem
from apps.email_agent.services import admin_imap

router = APIRouter(prefix="/email/mailbox", tags=["mailbox"])


def _check_allowed(email_addr: str) -> None:
    """Raise 403 if mailbox is not in the allowlist."""
    if not config.is_mailbox_readable(email_addr):
        raise HTTPException(
            status_code=403,
            detail=f"Mailbox {email_addr} is not in the read allowlist",
        )


@router.get("/{email_addr}/messages", response_model=list[MessageListItem])
async def list_messages(
    email_addr: str,
    folder: str = Query("INBOX"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None),
    _identity: str = Depends(verify_service_identity),
):
    """List messages in a mailbox folder."""
    _check_allowed(email_addr)
    result = await admin_imap.list_messages(
        email_addr, folder=folder, limit=limit, offset=offset, query=q
    )
    return [MessageListItem(**m) for m in result]


@router.get("/{email_addr}/message/{uid}")
async def get_message(
    email_addr: str,
    uid: str,
    folder: str = Query("INBOX"),
    _identity: str = Depends(verify_service_identity),
):
    """Fetch a full message with body and attachments."""
    _check_allowed(email_addr)
    msg = await admin_imap.fetch_message(email_addr, uid, folder=folder)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@router.get("/{email_addr}/message/{uid}/raw")
async def get_message_raw(
    email_addr: str,
    uid: str,
    folder: str = Query("INBOX"),
    _identity: str = Depends(verify_service_identity),
):
    """Fetch raw RFC822 message."""
    _check_allowed(email_addr)
    raw = await admin_imap.fetch_raw(email_addr, uid, folder=folder)
    if not raw:
        raise HTTPException(status_code=404, detail="Message not found")
    return Response(content=raw, media_type="message/rfc822")


@router.get("/{email_addr}/message/{uid}/attachment/{att_id}")
async def get_attachment(
    email_addr: str,
    uid: str,
    att_id: str,
    folder: str = Query("INBOX"),
    _identity: str = Depends(verify_service_identity),
):
    """Download an attachment."""
    _check_allowed(email_addr)
    result = await admin_imap.fetch_attachment(email_addr, uid, att_id, folder=folder)
    if not result:
        raise HTTPException(status_code=404, detail="Attachment not found")
    content, filename, content_type = result
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{email_addr}/message/{uid}/mark_read")
async def mark_read(
    email_addr: str,
    uid: str,
    folder: str = Query("INBOX"),
    _identity: str = Depends(verify_service_identity),
):
    """Mark a message as read."""
    _check_allowed(email_addr)
    ok = await admin_imap.mark_read(email_addr, uid, folder=folder)
    return {"ok": ok}


@router.post("/{email_addr}/message/{uid}/mark_unread")
async def mark_unread(
    email_addr: str,
    uid: str,
    folder: str = Query("INBOX"),
    _identity: str = Depends(verify_service_identity),
):
    """Mark a message as unread."""
    _check_allowed(email_addr)
    ok = await admin_imap.mark_unread(email_addr, uid, folder=folder)
    return {"ok": ok}
