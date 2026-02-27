"""
email_agent — inbox/message endpoints (IMAP).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from apps.email_agent.auth.identity import verify_service_identity
from apps.email_agent.schemas import MessageDetail, MessageSummary
from apps.email_agent.services import imap

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
    return [MessageSummary(**r) for r in results]


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
