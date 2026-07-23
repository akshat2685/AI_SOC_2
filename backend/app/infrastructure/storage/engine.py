import os
import structlog
from typing import Optional, Any
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
    AsyncSession,
)

try:
    from neo4j import AsyncGraphDatabase, AsyncDriver
except ImportError:
    AsyncGraphDatabase = None
    AsyncDriver = Any

try:
    from qdrant_client import AsyncQdrantClient
except ImportError:
    AsyncQdrantClient = Any

logger = structlog.get_logger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", os.getenv("POSTGRES_URL", "sqlite+aiosqlite:///./ai_soc.db"))
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

def create_storage_engine(url: str = DATABASE_URL) -> AsyncEngine:
    """
    Creates an async engine for PostgreSQL (asyncpg) or SQLite (aiosqlite).
    Configures appropriate connection pooling and dialect options.
    """
    if url.startswith("postgresql"):
        engine = create_async_engine(
            url,
            echo=False,
            future=True,
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            pool_pre_ping=True,
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
        )
    else:
        # Fallback to SQLite or other dialects
        engine = create_async_engine(
            url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False} if "sqlite" in url else {},
        )
    return engine

engine: AsyncEngine = create_storage_engine(DATABASE_URL)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

neo4j_driver: Optional[AsyncDriver] = None
if AsyncGraphDatabase:
    try:
        neo4j_driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    except Exception as e:
        logger.warning("neo4j_driver_init_failed", error=str(e), exc_info=True)

qdrant_client: Optional[AsyncQdrantClient] = None
if AsyncQdrantClient:
    try:
        qdrant_client = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY if QDRANT_API_KEY else None)
    except Exception as e:
        logger.warning("qdrant_client_init_failed", error=str(e), exc_info=True)

class StorageContext:
    """
    Unit-of-Work context that encapsulates SQLAlchemy, Neo4j, and Qdrant sessions.
    Injects native multi-modal clients alongside the relational AsyncSession.
    """
    def __init__(self, session: AsyncSession, neo4j: Optional[AsyncDriver] = None, qdrant: Optional[AsyncQdrantClient] = None):
        self.session = session
        self.neo4j = neo4j
        self.qdrant = qdrant

async def dispose_engine() -> None:
    """Closes and disposes of the storage engine connection pool."""
    if engine:
        await engine.dispose()
        logger.info("Storage engine connection pool disposed successfully.")
    
    global neo4j_driver
    if neo4j_driver:
        await neo4j_driver.close()
        logger.info("Neo4j driver disposed successfully.")
        
    global qdrant_client
    if qdrant_client:
        try:
            import inspect
            if hasattr(qdrant_client, "close"):
                if inspect.iscoroutinefunction(qdrant_client.close):
                    await qdrant_client.close()
                else:
                    qdrant_client.close()
            logger.info("Qdrant client disposed successfully.")
        except Exception as e:
            logger.warning(f"Error closing Qdrant client: {e}")
