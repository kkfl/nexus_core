"""
Email notification webhook — lets the portal fire Telegram alerts
for email operations without the remote email-agent needing to reach
notifications-agent directly.

POST /email-events  { action, details }
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.nexus_api.dependencies import get_current_user
from packages.shared.alerts import send_alert
from packages.shared.models import User

router = APIRouter()


class EmailEventIn(BaseModel):
    action: str  # e.g. "mailbox_create", "mailbox_disable", "mailbox_password", "alias_add"
    details: str  # e.g. "Mailbox: user@example.com"


_ALLOWED_ACTIONS = {"mailbox_create", "mailbox_disable", "mailbox_password", "alias_add"}


@router.post("/email-events", status_code=204)
async def email_event(
    body: EmailEventIn,
    current_user: User = Depends(get_current_user),
):
    """Fire a Telegram notification for an email admin operation."""
    if body.action not in _ALLOWED_ACTIONS:
        return  # silently ignore unknown actions
    send_alert(body.action, current_user.email, body.details)
