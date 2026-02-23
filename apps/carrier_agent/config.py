from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    nexus_base_url: str = "http://nexus-api:8000"
    nexus_agent_key: str = ""
    carrier_mock: bool = False
    vault_base_url: str = "http://secrets-agent:8007"
    vault_service_id: str = "carrier-agent"
    vault_agent_key: str = ""
    enable_docs: bool = False
    database_url: str = ""
    carrier_agent_keys: str = "{}"

    model_config = {"env_file": ".env", "extra": "ignore", "case_sensitive": False}


config = Settings()
