import json
import time
import logging
from app.core.config import settings

class AuditLogger:
    def __init__(self):
        self.producer = None
        self.topic = "soc_audit_log"
        
    async def start(self):
        try:
            from aiokafka import AIOKafkaProducer
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
            )
            await self.producer.start()
            logging.info("AuditLogger started")
        except Exception as e:
            logging.error(f"Failed to start AuditLogger: {e}")
        
    async def stop(self):
        if self.producer:
            await self.producer.stop()
            logging.info("AuditLogger stopped")

    def emit(self, action: str, tenant_id: int, user_id: int = None, trace_id: str = None, details: dict = None):
        """Asynchronously emit an event to Kafka."""
        import asyncio
        event = {
            "tenant_id": tenant_id,
            "action": action,
            "user_id": user_id,
            "trace_id": trace_id,
            "details": details or {},
            "timestamp": int(time.time() * 1000)
        }
        
        if self.producer:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.producer.send_and_wait(
                    self.topic,
                    key=str(tenant_id).encode('utf-8'),
                    value=json.dumps(event).encode('utf-8')
                ))
            except Exception as e:
                logging.error(f"Failed to emit audit log to Kafka: {e}")
        else:
            logging.warning(f"AuditLogger producer not initialized. Event: {event}")

audit_logger = AuditLogger()
