import json
import structlog
from typing import List, Dict, Any
import asyncio

try:
    from core.event_bus import create_event_bus
    from api.database import db
except ImportError:
    from intelligence_engine.core.event_bus import create_event_bus
    from intelligence_engine.api.database import db

logger = structlog.get_logger(__name__)

class DistributionEngine:
    def __init__(self, use_kafka: bool = True):
        backend = 'kafka' if use_kafka else 'in_memory'
        self.event_bus = create_event_bus(backend=backend)
        self.redis_client = db.get_redis_client()
        self.topic = "threat.intel.ingested"

    async def start(self):
        await self.event_bus.start()

    async def stop(self):
        await self.event_bus.stop()

    async def distribute(self, indicators: List[Dict[str, Any]]):
        """Distribute indicators to Kafka and Redis."""
        for indicator in indicators:
            try:
                # 1. Publish to Kafka
                await self.event_bus.publish(self.topic, indicator)
                
                # 2. Sync to Redis for real-time detection (O(1) lookups)
                # Key format: ti:{tenant_id}:{indicator_type}:{indicator_value}
                tenant_id = indicator.get('tenant_id', 'default')
                ind_type = indicator.get('indicator_type')
                ind_value = indicator.get('indicator_value')
                
                if ind_type and ind_value:
                    redis_key = f"ti:{tenant_id}:{ind_type}:{ind_value}"
                    # Store as JSON string, with 7 days expiration by default if not specified
                    expiration = 7 * 24 * 60 * 60 
                    self.redis_client.setex(redis_key, expiration, json.dumps(indicator))
            except Exception as e:
                logger.error(f"Error distributing indicator: {e}")
