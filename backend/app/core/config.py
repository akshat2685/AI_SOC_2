import logging
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

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
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    AUDIT_SECRET_KEY: str = ""

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"
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
        # Fail fast ONLY on SECRET_KEY. Every other integration degrades
        # gracefully with a warning so the MVP boots without optional
        # services configured.
        if not self.SECRET_KEY:
            raise ValueError(
                "Missing required environment variable: SECRET_KEY. "
                "Set it in .env or as a system environment variable. "
                'Example: export SECRET_KEY="$(openssl rand -hex 32)"'
            )
        degraded = {
            "GEMINI_API_KEY": "AI agent features (triage / investigation) are disabled",
            "GOOGLE_API_KEY": "Google API fallback for AI agents is disabled",
            "SOAR_API_KEY": "automated response actions are disabled",
            "SOAR_API_ENDPOINT": "automated response actions are disabled",
            "KAFKA_BOOTSTRAP_SERVERS": "event bus runs in-memory; streaming integrations disabled",
            "AUDIT_SECRET_KEY": "audit-log signing is disabled",
        }
        for key, consequence in degraded.items():
            if not getattr(self, key, ""):
                logger.warning("config degraded: %s not set -- %s", key, consequence)
        if not (self.POSTGRES_URL or self.DATABASE_URL):
            logger.warning(
                "config degraded: neither POSTGRES_URL nor DATABASE_URL is set -- "
                "using local SQLite fallback (./soc.db). Set POSTGRES_URL for production."
            )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
