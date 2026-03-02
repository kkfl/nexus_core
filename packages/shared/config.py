from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core Security
    NEXUS_MASTER_KEY: SecretStr = Field(
        ..., min_length=40, description="AES-GCM Master Key (Base64 encoded 32 bytes)"
    )
    # NOTE: Env var names match .env / .env.example — do NOT prefix with JWT_
    SECRET_KEY: str = Field(..., min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Environment
    ENVIRONMENT: str = "production"  # development | production

    # DB
    DATABASE_URL: str = Field(...)

    # Storage
    STORAGE_BACKEND_TYPE: str = "s3"
    STORAGE_S3_ENDPOINT: str | None = None
    STORAGE_S3_ACCESS_KEY: str | None = None
    STORAGE_S3_SECRET_KEY: str | None = None
    STORAGE_S3_BUCKET: str = "nexus-artifacts"
    STORAGE_S3_REGION: str = "us-east-1"

    # Feature Flags / Toggles
    ENABLE_DOCS: bool = False
    ENABLE_STORAGE_WRITES: bool = False
    ENABLE_DELETES: bool = False

    # HTTP
    CORS_ORIGINS: str = ""  # Comma separated

    # Redis
    REDIS_URL: str = Field(..., description="Redis connection URL for async workers")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
