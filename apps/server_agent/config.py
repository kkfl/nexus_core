"""
Server Agent configuration -- all values loaded from environment variables.
No defaults for secrets. No hardcoded values.
"""

from __future__ import annotations

import json

from pydantic_settings import BaseSettings


class ServerAgentSettings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus_pass@postgres:5432/nexus_core"

    # Service identity / auth
    server_agent_keys: str = "{}"

    # Vault / secrets-agent
    vault_base_url: str = "http://secrets-agent:8007"
    vault_service_id: str = "server-agent"
    vault_agent_key: str = ""

    # Observability
    log_level: str = "INFO"
    enable_docs: bool = False

    # Job execution
    job_max_attempts: int = 3
    job_base_delay_seconds: float = 1.0
    job_poll_interval: int = 5

    # Feature flags
    proxmox_enable_snapshots: bool = False

    # Provider defaults
    vultr_api_base: str = "https://api.vultr.com"
    proxmox_verify_ssl: bool = True

    # Sync
    sync_interval: int = 300

    # Redis
    redis_url: str = "redis://redis:6379/0"

    model_config = {"env_file": ".env", "extra": "ignore", "case_sensitive": False}

    def get_agent_keys(self) -> dict[str, str]:
        """Parse SERVER_AGENT_KEYS JSON map."""
        try:
            return json.loads(self.server_agent_keys)
        except (json.JSONDecodeError, TypeError):
            return {}


_settings: ServerAgentSettings | None = None


def get_settings() -> ServerAgentSettings:
    global _settings
    if _settings is None:
        _settings = ServerAgentSettings()
    return _settings
