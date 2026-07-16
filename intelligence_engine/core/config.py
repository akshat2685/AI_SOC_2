import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel
from functools import lru_cache

class DatabaseSettings(BaseModel):
    postgres_url: str = "postgresql://soc:changeme_in_production@localhost:5432/soc"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_auth: str = "neo4j/password_in_production"
    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6379"
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123

class AISettings(BaseModel):
    gemini_api_key: str = ""

class KafkaSettings(BaseModel):
    bootstrap_servers: str = "localhost:9092"

class SOARSettings(BaseModel):
    api_key: str = ""
    api_endpoint: str = ""

class APISettings(BaseModel):
    intelligence_engine_host: str = "localhost"
    intelligence_engine_port: int = 8001

class SecuritySettings(BaseModel):
    secret_key: str = "change_me_in_production"
    algorithm: str = "RS256"
    allowed_origins: list[str] = ["https://soc.example.com"]
    public_key_path: str = ""
    private_key_path: str = ""
    api_key_salt: str = "default_salt"

class Settings(BaseSettings):
    db: DatabaseSettings = DatabaseSettings()
    ai: AISettings = AISettings()
    kafka: KafkaSettings = KafkaSettings()
    soar: SOARSettings = SOARSettings()
    api: APISettings = APISettings()
    security: SecuritySettings = SecuritySettings()

    model_config = SettingsConfigDict(
        env_file='.env',
        env_nested_delimiter='__',
        extra='ignore'
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings(
        db=DatabaseSettings(
            postgres_url=os.getenv("POSTGRES_URL", "postgresql://soc:changeme_in_production@localhost:5432/soc"),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_auth=os.getenv("NEO4J_AUTH", "neo4j/password_in_production"),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            clickhouse_host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            clickhouse_port=int(os.getenv("CLICKHOUSE_PORT", "8123"))
        ),
        ai=AISettings(gemini_api_key=os.getenv("GEMINI_API_KEY", "")),
        kafka=KafkaSettings(bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")),
        soar=SOARSettings(
            api_key=os.getenv("SOAR_API_KEY", ""), 
            api_endpoint=os.getenv("SOAR_API_ENDPOINT", "")
        ),
        api=APISettings(
            intelligence_engine_host=os.getenv("INTELLIGENCE_ENGINE_HOST", "localhost"),
            intelligence_engine_port=int(os.getenv("INTELLIGENCE_ENGINE_PORT", "8001"))
        ),
        security=SecuritySettings(
            secret_key=os.getenv("SECRET_KEY", "change_me_in_production"),
            algorithm=os.getenv("JWT_ALGORITHM", "RS256"),
            allowed_origins=os.getenv("ALLOWED_ORIGINS", "https://soc.example.com").split(","),
            public_key_path=os.getenv("PUBLIC_KEY_PATH", ""),
            private_key_path=os.getenv("PRIVATE_KEY_PATH", ""),
            api_key_salt=os.getenv("API_KEY_SALT", "default_salt")
        )
    )
