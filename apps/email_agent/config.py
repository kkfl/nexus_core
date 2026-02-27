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


config = Settings()
