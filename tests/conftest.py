import os
import sys
import json
import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator

# Insert root and backend paths into sys.path
sys.path.insert(0, os.path.abspath("backend"))
sys.path.insert(0, os.path.abspath("."))

# Set required environment variables for test execution
os.environ.setdefault("GEMINI_API_KEY", "test_gemini_api_key_for_unit_tests")
os.environ.setdefault("SOAR_API_KEY", "test_soar_api_key")
os.environ.setdefault("SOAR_API_ENDPOINT", "https://api.test.example.com/v1/containment")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://soc_test:soc_test@localhost:5432/soc_test")
os.environ.setdefault("SECRET_KEY", "test_secret_key")
os.environ.setdefault("AUDIT_SECRET_KEY", "test_audit_secret")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("EVENT_BUS_BACKEND", "stub")
os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_AUTH", "neo4j/password")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.app.main import app
from backend.app.domain.models import Base, Alert, Incident, SeverityEnum, StatusEnum
from backend.app.infrastructure.database import get_db

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="function")
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide temporary in-memory async SQLite database for testing."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with async_session() as session:
        yield session
        
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def async_client(test_db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide AsyncClient pointing to FastAPI application with DB dependency override."""
    async def _get_test_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
