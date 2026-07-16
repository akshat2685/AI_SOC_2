import asyncio
import time
import logging
from typing import Dict, Any
from .config import get_settings

logger = logging.getLogger(__name__)

class HealthChecker:
    def __init__(self, registry=None):
        self.registry = registry
        self.settings = get_settings()
        
    async def check_postgres(self) -> Dict[str, Any]:
        start = time.time()
        try:
            try:
                from api.database import db
            except ImportError:
                from intelligence_engine.api.database import db
            # Ping database using a simple SELECT query
            db.execute_postgres("SELECT 1")
            latency = (time.time() - start) * 1000
            return {"status": "healthy", "latency_ms": latency}
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {"status": "unhealthy", "error": str(e), "latency_ms": latency}

    async def check_neo4j(self) -> Dict[str, Any]:
        start = time.time()
        try:
            try:
                from api.database import db
            except ImportError:
                from intelligence_engine.api.database import db
            db.execute_neo4j("RETURN 1")
            latency = (time.time() - start) * 1000
            return {"status": "healthy", "latency_ms": latency}
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {"status": "unhealthy", "error": str(e), "latency_ms": latency}

    async def check_qdrant(self) -> Dict[str, Any]:
        start = time.time()
        try:
            try:
                from api.database import db
            except ImportError:
                from intelligence_engine.api.database import db
            client = db.get_qdrant_client()
            client.get_collections()
            latency = (time.time() - start) * 1000
            return {"status": "healthy", "latency_ms": latency}
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {"status": "unhealthy", "error": str(e), "latency_ms": latency}
        
    async def check_kafka(self) -> Dict[str, Any]:
        start = time.time()
        try:
            from confluent_kafka import Consumer
            conf = {
                'bootstrap.servers': self.settings.kafka.bootstrap_servers,
                'group.id': 'healthcheck_temp',
                'auto.offset.reset': 'earliest',
                'socket.timeout.ms': 1000
            }
            c = Consumer(conf)
            c.list_topics(timeout=1.0)
            c.close()
            latency = (time.time() - start) * 1000
            return {"status": "healthy", "latency_ms": latency}
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {"status": "unhealthy", "error": str(e), "latency_ms": latency}
        
    async def check_redis(self) -> Dict[str, Any]:
        start = time.time()
        try:
            try:
                from api.database import db
            except ImportError:
                from intelligence_engine.api.database import db
            client = db.get_redis_client()
            client.ping()
            latency = (time.time() - start) * 1000
            return {"status": "healthy", "latency_ms": latency}
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {"status": "unhealthy", "error": str(e), "latency_ms": latency}

    async def check_clickhouse(self) -> Dict[str, Any]:
        start = time.time()
        try:
            try:
                from api.database import db
            except ImportError:
                from intelligence_engine.api.database import db
            db.execute_clickhouse("SELECT 1")
            latency = (time.time() - start) * 1000
            return {"status": "healthy", "latency_ms": latency}
        except Exception as e:
            latency = (time.time() - start) * 1000
            return {"status": "unhealthy", "error": str(e), "latency_ms": latency}
        
    async def aggregate(self) -> Dict[str, Any]:
        results = await asyncio.gather(
            self.check_postgres(),
            self.check_neo4j(),
            self.check_qdrant(),
            self.check_kafka(),
            self.check_redis(),
            self.check_clickhouse(),
            return_exceptions=True
        )
        
        services = ["postgres", "neo4j", "qdrant", "kafka", "redis", "clickhouse"]
        health_details = {}
        overall_healthy = True
        
        for name, res in zip(services, results):
            if isinstance(res, Exception):
                health_details[name] = {"status": "error", "error": str(res)}
                overall_healthy = False
            else:
                health_details[name] = res
                if res.get("status") != "healthy":
                    overall_healthy = False
                    
        return {
            "overall": "healthy" if overall_healthy else "unhealthy",
            "services": health_details
        }
