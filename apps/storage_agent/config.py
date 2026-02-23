from typing import Dict, List
import os
import json
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "storage-agent"
    service_version: str = "1.0.0"
    env: str = "prod"
    
    # Nexus + Agent Registry
    nexus_base_url: str = "http://nexus-api:8000"
    registry_base_url: str = "http://agent-registry:8012"
    nexus_registry_agent_key: str = ""
    
    # Secrets
    vault_base_url: str = "http://secrets-agent:8007"
    vault_service_id: str = "storage-agent"
    vault_agent_key: str = ""
    
    # DB + Notifications
    database_url: str = "sqlite+aiosqlite:///./storage_agent.db"
    notifications_base_url: str = "http://notifications-agent:8008"
    
    # Allowed callers map for /v1 (JSON dict)
    storage_agent_keys: str = "{}"
    
    # CORS
    cors_origins: str = ""

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "case_sensitive": False
    }

    def get_cors_origins(self) -> List[str]:
        if not self.cors_origins:
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        
    def get_agent_keys(self) -> Dict[str, str]:
        if not self.storage_agent_keys:
            return {}
        try:
            return json.loads(self.storage_agent_keys)
        except Exception:
            return {}

_settings = Settings()

def get_settings() -> Settings:
    return _settings
