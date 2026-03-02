"""
email_agent — inbox/message endpoints (IMAP).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from apps.email_agent.auth.identity import verify_service_identity
from apps.email_agent.schemas import MessageDetail, MessageSummary
from apps.email_agent.services import imap
from packages.shared.events.api import emit_event

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/email", tags=["inbox"])


@router.get("/inbox/search", response_model=list[MessageSummary])
async def search_inbox(
    query: str | None = Query(None, description="Search subject"),
    since: str | None = Query(None, description="IMAP date, e.g. 25-Feb-2026"),
    limit: int = Query(50, le=200),
    folder: str = Query("INBOX"),
    _identity: str = Depends(verify_service_identity),
):
    """Search messages in the ingest mailbox."""
    results = await imap.search_inbox(query=query, since=since, limit=limit, folder=folder)
    summaries = [MessageSummary(**r) for r in results]

    if summaries:
        try:
            await emit_event(
                event_type="email.inbox.searched",
                payload={"folder": folder, "count": len(summaries), "query": query or ""},
                produced_by="email-agent",
                tags=["email", "inbox", "search"],
            )
        except Exception:
            logger.warning("event_emit_failed", event_type="email.inbox.searched")

    return summaries


@router.get("/message/{msg_id}", response_model=MessageDetail)
async def get_message(
    msg_id: str,
    folder: str = Query("INBOX"),
    _identity: str = Depends(verify_service_identity),
):
    """Fetch a full message by IMAP sequence number."""
    msg = await imap.fetch_message(msg_id, folder=folder)
    if not msg:
        return Response(status_code=404, content='{"error":"message not found"}')

    try:
        await emit_event(
            event_type="email.message.read",
            payload={"msg_id": msg_id, "folder": folder, "subject": msg.get("subject", "")[:100]},
            produced_by="email-agent",
            tags=["email", "message", "read"],
        )
    except Exception:
        logger.warning("event_emit_failed", event_type="email.message.read")

    return MessageDetail(**msg)


@router.get("/message/{msg_id}/raw")
async def get_message_raw(
    msg_id: str,
    folder: str = Query("INBOX"),
    _identity: str = Depends(verify_service_identity),
):
    """Fetch raw RFC822 EML."""
    raw = await imap.fetch_raw(msg_id, folder=folder)
    if not raw:
        return Response(status_code=404, content='{"error":"message not found"}')
    return Response(content=raw, media_type="message/rfc822")


@router.get("/message/{msg_id}/attachments/{attachment_id}")
async def get_attachment(
    msg_id: str,
    attachment_id: str,
    _identity: str = Depends(verify_service_identity),
):
    """Fetch an attachment (placeholder — requires object storage)."""
    return Response(
        status_code=501,
        content='{"error":"attachment retrieval from object storage not yet implemented"}',
    )
