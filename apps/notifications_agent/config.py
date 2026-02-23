"""
notifications_agent — pydantic-settings config.
All runtime values come from environment variables; no hardcoded secrets.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus_pass@postgres:5432/nexus_core"

    # Auth — callers of notifications_agent
    notifications_agent_keys: str = "{}"  # JSON map: {"nexus": "key", "admin": "admin-key"}

    # Vault (secrets_agent)
    vault_base_url: str = "http://secrets-agent:8007"
    vault_service_id: str = "notifications-agent"
    vault_agent_key: str = ""

    # Job queue
    job_max_attempts: int = 3
    job_retry_base_delay: float = 1.0
    job_idempotency_ttl_hours: int = 24

    # Misc
    enable_docs: bool = False
    cors_origins: str = ""
    service_version: str = "1.0.0"

    model_config = {"env_file": ".env", "extra": "ignore", "case_sensitive": False}

    def get_agent_keys(self) -> dict[str, str]:
        import json

        try:
            return json.loads(self.notifications_agent_keys)
        except Exception:
            return {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
