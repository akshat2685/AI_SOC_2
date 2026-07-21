import asyncio
import json
import logging
import hmac
import hashlib
from typing import Dict

from sqlalchemy import text, select
from app.core.config import settings
from app.infrastructure.database import AsyncSessionLocal
from app.domain.models import AuditEvent

logger = logging.getLogger(__name__)

class AuditConsumer:
    def __init__(self):
        self.topic = "soc_audit_log"
        self.dlq_topic = "soc_audit_log_dlq"
        self.consumer = None
        self.producer = None
        self.tenant_hashes: Dict[int, str] = {}
        
    async def _compute_hash(self, tenant_id: int, event_data: dict) -> str:
        if tenant_id not in self.tenant_hashes:
            async with AsyncSessionLocal() as session:
                stmt = select(AuditEvent.integrity_hash).where(AuditEvent.tenant_id == tenant_id).order_by(AuditEvent.id.desc()).limit(1)
                result = await session.execute(stmt)
                latest_hash = result.scalar_one_or_none()
                self.tenant_hashes[tenant_id] = latest_hash if latest_hash else "0"
        
        previous_hash = self.tenant_hashes[tenant_id]
        
        canonical_event = json.dumps(event_data, separators=(',', ':'), sort_keys=True)
        message = f"{previous_hash}{canonical_event}".encode('utf-8')
        
        secret = settings.AUDIT_SECRET_KEY.encode('utf-8')
        new_hash = hmac.new(secret, message, hashlib.sha256).hexdigest()
        
        self.tenant_hashes[tenant_id] = new_hash
        return new_hash

    async def start(self):
        try:
            from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id="audit_consumer_group",
                auto_offset_reset="earliest"
            )
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
            )
            
            await self.consumer.start()
            await self.producer.start()
            
            logger.info("AuditConsumer started listening.")
            asyncio.create_task(self._consume_loop())
        except Exception as e:
            logger.error(f"Failed to start AuditConsumer: {e}")

    async def _consume_loop(self):
        try:
            async for msg in self.consumer:
                try:
                    event_data = json.loads(msg.value.decode('utf-8'))
                    tenant_id = event_data["tenant_id"]
                    
                    integrity_hash = await self._compute_hash(tenant_id, event_data)
                    event_data["integrity_hash"] = integrity_hash
                    
                    await self._sink_to_postgres(tenant_id, event_data)
                    await self._sink_to_clickhouse(event_data)
                except Exception as e:
                    logger.error(f"Failed to process audit event, sending to DLQ: {e}")
                    if self.producer:
                        await self.producer.send_and_wait(
                            self.dlq_topic,
                            key=msg.key,
                            value=msg.value
                        )
        except Exception as e:
            logger.error(f"AuditConsumer loop error: {e}")

    async def _sink_to_postgres(self, tenant_id: int, event_data: dict):
        async with AsyncSessionLocal() as session:
            # Setup RLS safely using parameterized bindings
            await session.execute(text("SELECT set_config('rls.tenant_id', :tenant_id, true);"), {"tenant_id": str(tenant_id)})
            
            new_event = AuditEvent(
                tenant_id=tenant_id,
                user_id=event_data.get("user_id"),
                trace_id=event_data.get("trace_id"),
                action=event_data.get("action"),
                details=event_data.get("details", {}),
                integrity_hash=event_data["integrity_hash"]
            )
            session.add(new_event)
            await session.commit()

    async def _sink_to_clickhouse(self, event_data: dict):
        # Simulate ClickHouse sink for now
        pass

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
