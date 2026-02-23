from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API/Agent Info
    port: int = 8004
    service_name: str = "monitoring-agent"
    service_version: str = "1.0.0"
    environment: str = "development"
    
    # Auth
    monitoring_agent_keys: dict[str, str] = {}  # Inbound API keys
    
    # Internal Agent Auth (outbound)
    registry_base_url: str = "http://agent-registry:8012"
    nexus_registry_agent_key: str = "nexus-registry-key"

    # Secrets Agent Auth (for fetching outbound keys)
    vault_base_url: str = "http://secrets-agent:8007"
    vault_service_id: str = "monitoring-agent"
    vault_agent_key: str = "monitoring-vault-key-change-me"
    
    # Notifications Auth (to send alerts)
    notifications_base_url: str = "http://notifications-agent:8008"

    # CORS & Docs
    cors_origins: str = "*"
    enable_docs: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

config = Settings()

def get_settings() -> Settings:
    return config
