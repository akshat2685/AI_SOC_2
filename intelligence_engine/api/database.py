import structlog
from typing import Any, Dict, List, Optional

try:
    from core.config import get_settings
except ImportError:
    from intelligence_engine.core.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

try:
    from core.optimizations import async_wrap, content_hash_cache, async_content_hash_cache
except ImportError:
    try:
        from intelligence_engine.core.optimizations import async_wrap, content_hash_cache, async_content_hash_cache
    except ImportError:
        def async_wrap(func):
            import asyncio, functools
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
            return wrapper
        def content_hash_cache(func):
            return func
        def async_content_hash_cache(func):
            return func

# Try imports with graceful fallback
try:
    import psycopg2
    from psycopg2 import pool
except ImportError:
    psycopg2 = None
    logger.warning("psycopg2 is not installed. PostgreSQL helper will be unavailable.")

try:
    import clickhouse_connect
except ImportError:
    clickhouse_connect = None
    logger.warning("clickhouse_connect is not installed. ClickHouse helper will be unavailable.")

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None
    logger.warning("neo4j is not installed. Neo4j helper will be unavailable.")

try:
    from qdrant_client import QdrantClient
except ImportError:
    QdrantClient = None
    logger.warning("qdrant-client is not installed. Qdrant helper will be unavailable.")

try:
    import redis
except ImportError:
    redis = None
    logger.warning("redis is not installed. Redis helper will be unavailable.")


class DatabaseManager:
    """Manages connections and query helpers for PostgreSQL, ClickHouse, Neo4j, Qdrant, and Redis."""
    
    def __init__(self):
        self._postgres_pool = None
        self._neo4j_driver = None
        self._redis_client = None
        self._qdrant_client = None
        self._clickhouse_client = None

    def init_postgres(self):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed.")
        if self._postgres_pool is None:
            try:
                self._postgres_pool = psycopg2.pool.ThreadedConnectionPool(
                    1, 10, dsn=settings.db.postgres_url
                )
                logger.info("PostgreSQL connection pool initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL pool: {e}")
                raise

    def get_postgres_connection(self):
        self.init_postgres()
        return self._postgres_pool.getconn()

    def release_postgres_connection(self, conn):
        if self._postgres_pool and conn:
            self._postgres_pool.putconn(conn)

    def execute_postgres(self, query: str, params: Optional[tuple] = None, fetch: bool = True) -> Any:
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed.")
        conn = None
        try:
            conn = self.get_postgres_connection()
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch:
                    return cursor.fetchall()
                conn.commit()
                return None
        except Exception as e:
            logger.error(f"PostgreSQL query execution failed: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.release_postgres_connection(conn)

    @async_wrap
    async def aexecute_postgres(self, query: str, params: Optional[tuple] = None, fetch: bool = True) -> Any:
        return self.execute_postgres(query, params, fetch)

    def get_clickhouse_client(self):
        if clickhouse_connect is None:
            raise RuntimeError("clickhouse_connect is not installed.")
        if self._clickhouse_client is None:
            try:
                self._clickhouse_client = clickhouse_connect.get_client(
                    host=settings.db.clickhouse_host,
                    port=settings.db.clickhouse_port,
                    username="default",
                    password=""
                )
                logger.info("ClickHouse client connected.")
            except Exception as e:
                logger.error(f"ClickHouse client connection failed: {e}")
                raise
        return self._clickhouse_client

    def execute_clickhouse(self, query: str) -> List[Any]:
        client = self.get_clickhouse_client()
        try:
            result = client.query(query)
            return result.result_rows
        except Exception as e:
            logger.error(f"ClickHouse query execution failed: {e}")
            raise

    @async_content_hash_cache
    async def aexecute_clickhouse(self, query: str) -> List[Any]:
        import asyncio, functools
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self.execute_clickhouse, query))

    def get_neo4j_driver(self):
        if GraphDatabase is None:
            raise RuntimeError("neo4j driver is not installed.")
        if self._neo4j_driver is None:
            try:
                auth_str = settings.db.neo4j_auth
                if "/" in auth_str:
                    username, password = auth_str.split("/", 1)
                else:
                    username, password = "neo4j", auth_str
                
                self._neo4j_driver = GraphDatabase.driver(
                    settings.db.neo4j_uri,
                    auth=(username, password)
                )
                logger.info("Neo4j driver initialized.")
            except Exception as e:
                logger.error(f"Neo4j driver initialization failed: {e}")
                raise
        return self._neo4j_driver

    def execute_neo4j(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Any]:
        driver = self.get_neo4j_driver()
        try:
            with driver.session() as session:
                result = session.run(query, parameters)
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Neo4j query execution failed: {e}")
            raise

    @async_content_hash_cache
    async def aexecute_neo4j(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Any]:
        import asyncio, functools
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self.execute_neo4j, query, parameters))

    def get_qdrant_client(self) -> QdrantClient:
        if QdrantClient is None:
            raise RuntimeError("qdrant-client is not installed.")
        if self._qdrant_client is None:
            try:
                self._qdrant_client = QdrantClient(url=settings.db.qdrant_url)
                logger.info("Qdrant client initialized.")
            except Exception as e:
                logger.error(f"Qdrant client initialization failed: {e}")
                raise
        return self._qdrant_client

    def get_redis_client(self):
        if redis is None:
            raise RuntimeError("redis is not installed.")
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(settings.db.redis_url, decode_responses=True)
                logger.info("Redis client initialized.")
            except Exception as e:
                logger.error(f"Redis client initialization failed: {e}")
                raise
        return self._redis_client

    def close_all(self):
        """Clean up connections/pools."""
        if self._postgres_pool:
            try:
                self._postgres_pool.closeall()
                logger.info("PostgreSQL connections closed.")
            except Exception as e:
                logger.error(f"Failed to close PostgreSQL pool: {e}")
        if self._clickhouse_client:
            try:
                if hasattr(self._clickhouse_client, "close") and callable(self._clickhouse_client.close):
                    self._clickhouse_client.close()
                logger.info("ClickHouse client closed.")
            except Exception as e:
                logger.error(f"Failed to close ClickHouse client: {e}")
        if self._neo4j_driver:
            try:
                self._neo4j_driver.close()
                logger.info("Neo4j driver closed.")
            except Exception as e:
                logger.error(f"Failed to close Neo4j driver: {e}")
        if self._qdrant_client:
            try:
                if hasattr(self._qdrant_client, "close") and callable(self._qdrant_client.close):
                    self._qdrant_client.close()
                logger.info("Qdrant client closed.")
            except Exception as e:
                logger.error(f"Failed to close Qdrant client: {e}")
        if self._redis_client:
            try:
                self._redis_client.close()
                logger.info("Redis client closed.")
            except Exception as e:
                logger.error(f"Failed to close Redis client: {e}")

# Global db instance for import/use in routers
db = DatabaseManager()
