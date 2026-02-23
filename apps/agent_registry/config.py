from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    agent_registry_keys: str = "{}"  # JSON string mapping service_id -> agent_key
    enable_docs: bool = False

    model_config = {"env_file": ".env", "extra": "ignore", "case_sensitive": False}

    def get_agent_keys(self) -> dict[str, str]:
        import json

        try:
            return json.loads(self.agent_registry_keys)
        except Exception:
            return {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
