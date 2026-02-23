from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API/Agent Info
    port: int = 8013
    service_name: str = "automation-agent"
    environment: str = "development"
    
    # Auth
    nexus_master_key: str = "change_this_to_a_random_secure_string_for_jwts"
    automation_agent_keys: dict[str, str] = {}  # e.g. {"nexus": "nexus-automation-key"}
    
    # Internal Agent Auth (for outbound calls to agent_registry, secrets_agent, notifications_agent, etc.)
    nexus_base_url: str = "http://nexus-api:8000"
    nexus_agent_key: str = "internal-automation-key"
    registry_base_url: str = "http://agent-registry:8012"
    nexus_registry_agent_key: str = "nexus-registry-key"
    automation_vault_agent_key: str = "automation-vault-key-change-me"
    automation_dns_agent_key: str = "automation-dns-key-change-me"
    automation_pbx_agent_key: str = "automation-pbx-key-change-me"

    # Database setup (queue, run tracking)
    database_url: str = "postgresql+asyncpg://nexus:nexus_pass@localhost:5432/nexus_core"
    
    # Scheduler & Executor Limits
    max_concurrent_runs_global: int = 10
    dlq_max_replays: int = 3
    cron_tick_interval_seconds: int = 10

    class Config:
        env_file = ".env"
        extra = "ignore"

config = Settings()
