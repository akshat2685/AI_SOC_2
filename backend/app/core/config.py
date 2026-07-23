import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional

def get_required_env(key: str, default: Optional[str] = None) -> str:
    """Fail-fast validation: raise RuntimeError if required env var is missing and no default provided."""
    value = os.getenv(key, default)
    if not value:
        raise RuntimeError(
            f"Required environment variable {key} is not set.\n"
            f"Please set this variable in .env or as system environment variable.\n"
            f"Example: export {key}=\"your-value-here\""
        )
    return value

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI SOC Backend"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    AUDIT_SECRET_KEY: str = ""

    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    SOAR_API_KEY: str = ""
    SOAR_API_ENDPOINT: str = ""
    POSTGRES_URL: str = ""
    DATABASE_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        required_secrets = {
            "GEMINI_API_KEY": self.GEMINI_API_KEY,
            "SOAR_API_KEY": self.SOAR_API_KEY,
            "SOAR_API_ENDPOINT": self.SOAR_API_ENDPOINT,
            "POSTGRES_URL": self.POSTGRES_URL,
            "SECRET_KEY": self.SECRET_KEY,
            "KAFKA_BOOTSTRAP_SERVERS": self.KAFKA_BOOTSTRAP_SERVERS,
            "AUDIT_SECRET_KEY": self.AUDIT_SECRET_KEY,
        }
        missing = [k for k, v in required_secrets.items() if not v]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Set them in .env or as system environment variables."
            )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
