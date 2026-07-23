import json
import structlog
import asyncio
from typing import Optional

try:
    from aiokafka import AIOKafkaConsumer
except ImportError:
    AIOKafkaConsumer = None

from .graph_manager import TwinGraphManager

logger = structlog.get_logger(__name__)

class TwinSyncConsumer:
    """
    Kafka consumer to synchronize real-time asset changes from the event bus
    into the Neo4j Digital Twin.
    """
    def __init__(self, graph_manager: TwinGraphManager, bootstrap_servers: str = "localhost:9092"):
        self.graph_manager = graph_manager
        self.bootstrap_servers = bootstrap_servers
        self.consumer: Optional[Any] = None
        self._running = False

    async def start(self):
        if not AIOKafkaConsumer:
            logger.warning("aiokafka not installed, TwinSyncConsumer will not start.")
            return

        try:
            self.consumer = AIOKafkaConsumer(
                "asset.state.changed",
                bootstrap_servers=self.bootstrap_servers,
                group_id="digital_twin_sync_group"
            )
            await self.consumer.start()
            self._running = True
            asyncio.create_task(self._consume_loop())
            logger.info("TwinSyncConsumer started.")
        except Exception as e:
            logger.error(f"TwinSyncConsumer failed to start: {e}")

    async def stop(self):
        self._running = False
        if self.consumer:
            await self.consumer.stop()
            logger.info("TwinSyncConsumer stopped.")

    async def _consume_loop(self):
        try:
            async for msg in self.consumer:
                if not self._running:
                    break
                await self._process_message(msg)
        except Exception as e:
            logger.error(f"Error in TwinSyncConsumer loop: {e}")

    async def _process_message(self, msg):
        try:
            data = json.loads(msg.value.decode("utf-8"))
            tenant_id = data.get("tenant_id")
            event_type = data.get("event_type")
            payload = data.get("payload")

            if not tenant_id or not payload:
                return

            if event_type == "ASSET_UPSERT":
                await self.graph_manager.bulk_upsert_assets(tenant_id, payload)
            elif event_type == "RELATIONSHIP_UPSERT":
                await self.graph_manager.bulk_upsert_relationships(tenant_id, payload)
            else:
                logger.debug(f"Unhandled event type: {event_type}")

        except Exception as e:
            logger.error(f"Failed to process sync message: {e}")
