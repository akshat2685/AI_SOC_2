from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI SOC Backend"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "your-super-secret-key-that-should-be-changed"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    AUDIT_SECRET_KEY: str = "audit-secret-key-change-in-prod"
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

