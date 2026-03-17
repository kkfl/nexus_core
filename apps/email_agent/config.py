"""
email_agent — configuration.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8014
    database_url: str = "postgresql+asyncpg://nexus:nexus@nexus-postgres:5432/nexus_core"
    vault_base_url: str = "http://secrets-agent:8007"
    vault_service_id: str = "email-agent"
    vault_agent_key: str = "email-vault-key-change-me"
    enable_docs: bool = True

    # Mailbox drill-down security
    mailbox_read_allowlist: str = (
        ""  # comma-separated: "nexus-inbox@gsmcall.com,support@gsmcall.com"
    )
    allow_read_all_mailboxes: bool = True

    # Stats cache
    stats_cache_ttl_seconds: int = 60

    def get_allowed_mailboxes(self) -> list[str]:
        """Parse allowlist into a list of emails/domains."""
        if not self.mailbox_read_allowlist:
            return []
        return [e.strip().lower() for e in self.mailbox_read_allowlist.split(",") if e.strip()]

    def is_mailbox_readable(self, email: str) -> bool:
        """Check if a mailbox is allowed for drill-down reading."""
        if self.allow_read_all_mailboxes:
            return True
        allowed = self.get_allowed_mailboxes()
        if not allowed:
            return False
        email_lower = email.lower()
        for entry in allowed:
            if entry.startswith("@"):
                # Domain match
                if email_lower.endswith(entry):
                    return True
            elif email_lower == entry:
                return True
        return False


config = Settings()
