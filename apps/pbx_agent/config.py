"""
pbx_agent configuration — pydantic-settings.
All sensitive values (AMI secrets, SSH keys) are fetched at runtime from secrets-agent.
Only non-sensitive config + alias names live here.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    # Service
    port: int = 8011
    service_name: str = "pbx-agent"
    environment: str = "development"
    enable_docs: bool = False

    # Inbound auth — JSON map of service_id -> api_key
    # e.g. {"nexus":"key1","admin":"key2","automation-agent":"key3"}
    pbx_agent_keys: str = "{}"

    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus_pass@postgres:5432/nexus_core"

    # Agent Registry
    registry_base_url: str = "http://agent-registry:8012"
    nexus_registry_agent_key: str = ""

    # Secrets Agent (pbx-agent calls secrets to retrieve AMI creds at runtime)
    vault_base_url: str = "http://secrets-agent:8007"
    vault_service_id: str = "pbx-agent"
    pbx_vault_agent_key: str = Field(
        default="",
        validation_alias=AliasChoices("pbx_vault_agent_key", "vault_agent_key"),
    )

    # Notifications Agent
    notifications_base_url: str = "http://notifications-agent:8008"
    pbx_notif_agent_key: str = ""  # key pbx-agent uses to call notifications-agent

    # Mock mode — serve fixtures instead of live AMI
    pbx_mock: bool = False

    # Job worker
    job_worker_tick_seconds: int = 3
    job_max_attempts: int = 3

    model_config = {"env_file": ".env", "extra": "ignore", "case_sensitive": False}


config = Config()
