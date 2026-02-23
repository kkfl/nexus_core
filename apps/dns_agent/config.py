"""
DNS Agent configuration — all values loaded from environment variables.
No defaults for secrets. No hardcoded values.
"""

from __future__ import annotations

import json

from pydantic_settings import BaseSettings


class DnsAgentSettings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus_pass@postgres:5432/nexus_core"

    # Service identity / auth
    # JSON map of service_id -> api_key for callers allowed to use dns-agent
    # e.g. '{"nexus":"nexus-dns-key","admin":"admin-dns-key"}'
    dns_agent_keys: str = "{}"

    # Vault / secrets-agent
    vault_base_url: str = "http://secrets-agent:8007"
    vault_service_id: str = "dns-agent"
    vault_agent_key: str = ""

    # Observability
    log_level: str = "INFO"
    enable_docs: bool = False

    # Job execution
    job_max_attempts: int = 3
    job_base_delay_seconds: float = 0.5

    model_config = {"env_file": ".env", "extra": "ignore", "case_sensitive": False}

    def get_agent_keys(self) -> dict[str, str]:
        """Parse DNS_AGENT_KEYS JSON map."""
        try:
            return json.loads(self.dns_agent_keys)
        except (json.JSONDecodeError, TypeError):
            return {}


_settings: DnsAgentSettings | None = None


def get_settings() -> DnsAgentSettings:
    global _settings
    if _settings is None:
        _settings = DnsAgentSettings()
    return _settings
