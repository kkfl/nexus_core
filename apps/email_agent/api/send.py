"""
email_agent — send endpoints.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from apps.email_agent.auth.identity import verify_service_identity
from apps.email_agent.schemas import SendRequest, SendResponse, TestSendRequest
from apps.email_agent.services import smtp
from packages.shared.events.api import emit_event

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/email", tags=["send"])


@router.post("/test_send", response_model=SendResponse)
async def test_send(
    req: TestSendRequest,
    _identity: str = Depends(verify_service_identity),
):
    """Quick test send to a single recipient."""
    result = await smtp.send_email(
        to=[req.to],
        subject=req.subject,
        body_text=req.body_text,
    )

    try:
        await emit_event(
            event_type="email.message.sent",
            payload={"to": [req.to], "subject": req.subject, "test": True},
            produced_by="email-agent",
            tags=["email", "send", "test"],
        )
    except Exception:
        logger.warning("event_emit_failed", event_type="email.message.sent")

    return SendResponse(**result)


@router.post("/send", response_model=SendResponse)
async def send_email(
    req: SendRequest,
    _identity: str = Depends(verify_service_identity),
):
    """Full send with To/Cc/Bcc support."""
    result = await smtp.send_email(
        to=req.to,
        cc=req.cc or None,
        bcc=req.bcc or None,
        subject=req.subject,
        body_text=req.body_text,
        body_html=req.body_html,
    )

    try:
        await emit_event(
            event_type="email.message.sent",
            payload={"to": req.to, "subject": req.subject, "test": False},
            produced_by="email-agent",
            tags=["email", "send"],
        )
    except Exception:
        logger.warning("event_emit_failed", event_type="email.message.sent")

    return SendResponse(**result)

