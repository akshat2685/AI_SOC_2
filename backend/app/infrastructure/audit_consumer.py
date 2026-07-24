import asyncio
import json
import os
import structlog
import hmac
import hashlib
from typing import Dict, List

from sqlalchemy import text, select
from app.core.config import settings
from app.infrastructure.database import AsyncSessionLocal
from app.domain.models import AuditEvent

logger = structlog.get_logger(__name__)

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "shieldai")
CLICKHOUSE_TABLE = os.getenv("CLICKHOUSE_AUDIT_TABLE", "audit_events")
CLICKHOUSE_BATCH_SIZE = int(os.getenv("CLICKHOUSE_BATCH_SIZE", "100"))


class AuditConsumer:
    def __init__(self):
        self.topic = "soc_audit_log"
        self.dlq_topic = "soc_audit_log_dlq"
        self.consumer = None
        self.producer = None
        self.tenant_hashes: Dict[int, str] = {}
        self._ch_client = None
        self._pending_batch: List[dict] = []

    # ------------------------------------------------------------------
    # ClickHouse client (lazy init)
    # ------------------------------------------------------------------

    def _get_clickhouse_client(self):
        if self._ch_client is None:
            try:
                from clickhouse_connect import get_client

                self._ch_client = get_client(
                    host=CLICKHOUSE_HOST,
                    port=CLICKHOUSE_PORT,
                    database=CLICKHOUSE_DB,
                    username=os.getenv("CLICKHOUSE_USER", "default"),
                    password=os.getenv("CLICKHOUSE_PASSWORD", ""),
                )
                logger.info("clickhouse_connected", host=CLICKHOUSE_HOST, db=CLICKHOUSE_DB)
            except Exception as exc:
                logger.error("clickhouse_init_failed", error=str(exc))
                raise
        return self._ch_client

    # ------------------------------------------------------------------
    # HMAC chain-of-custody hashing
    # ------------------------------------------------------------------

    async def _compute_hash(self, tenant_id: int, event_data: dict) -> str:
        if tenant_id not in self.tenant_hashes:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AuditEvent.integrity_hash)
                    .where(AuditEvent.tenant_id == tenant_id)
                    .order_by(AuditEvent.id.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                latest_hash = result.scalar_one_or_none()
                self.tenant_hashes[tenant_id] = latest_hash if latest_hash else "0"

        previous_hash = self.tenant_hashes[tenant_id]
        canonical_event = json.dumps(event_data, separators=(",", ":"), sort_keys=True)
        message = f"{previous_hash}{canonical_event}".encode("utf-8")
        secret = settings.AUDIT_SECRET_KEY.encode("utf-8")
        new_hash = hmac.new(secret, message, hashlib.sha256).hexdigest()
        self.tenant_hashes[tenant_id] = new_hash
        return new_hash

    # ------------------------------------------------------------------
    # Kafka lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        try:
            from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id="audit_consumer_group",
                auto_offset_reset="earliest",
            )
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
            )
            await self.consumer.start()
            await self.producer.start()
            logger.info("audit_consumer_started")
            asyncio.create_task(self._consume_loop())
        except Exception as e:
            logger.error("audit_consumer_start_failed", error=str(e))

    async def _consume_loop(self):
        try:
            async for msg in self.consumer:
                try:
                    event_data = json.loads(msg.value.decode("utf-8"))
                    tenant_id = event_data["tenant_id"]

                    integrity_hash = await self._compute_hash(tenant_id, event_data)
                    event_data["integrity_hash"] = integrity_hash

                    await self._sink_to_postgres(tenant_id, event_data)
                    await self._sink_to_clickhouse(event_data)
                except Exception as e:
                    logger.error("audit_event_dlq", error=str(e))
                    if self.producer:
                        await self.producer.send_and_wait(
                            self.dlq_topic, key=msg.key, value=msg.value
                        )
        except Exception as e:
            logger.error("audit_consumer_loop_error", error=str(e))

    # ------------------------------------------------------------------
    # Sinks
    # ------------------------------------------------------------------

    async def _sink_to_postgres(self, tenant_id: int, event_data: dict):
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("SELECT set_config('rls.tenant_id', :tid, true);"),
                {"tid": str(tenant_id)},
            )
            new_event = AuditEvent(
                tenant_id=tenant_id,
                user_id=event_data.get("user_id"),
                trace_id=event_data.get("trace_id"),
                action=event_data.get("action"),
                details=event_data.get("details", {}),
                integrity_hash=event_data["integrity_hash"],
            )
            session.add(new_event)
            await session.commit()

    async def _sink_to_clickhouse(self, event_data: dict) -> None:
        """Batch-insert audit events into ClickHouse for compliance analytics."""
        self._pending_batch.append(event_data)

        if len(self._pending_batch) >= CLICKHOUSE_BATCH_SIZE:
            await self._flush_clickhouse_batch()

    async def _flush_clickhouse_batch(self) -> None:
        if not self._pending_batch:
            return

        batch = list(self._pending_batch)
        self._pending_batch.clear()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = self._get_clickhouse_client()
                rows = [
                    [
                        e.get("tenant_id"),
                        e.get("user_id"),
                        e.get("trace_id"),
                        e.get("action"),
                        json.dumps(e.get("details", {})),
                        e.get("integrity_hash"),
                        e.get("timestamp"),
                    ]
                    for e in batch
                ]
                columns = [
                    "tenant_id", "user_id", "trace_id", "action",
                    "details", "integrity_hash", "timestamp",
                ]
                client.insert(CLICKHOUSE_TABLE, rows, column_names=columns)
                logger.info("clickhouse_batch_flushed", count=len(batch))
                return
            except Exception as exc:
                if attempt == max_retries - 1:
                    logger.error(
                        "clickhouse_batch_failed_dlq",
                        error=str(exc),
                        count=len(batch),
                    )
                    # Route failed batch to DLQ so data isn't silently lost
                    if self.producer:
                        for event in batch:
                            await self.producer.send_and_wait(
                                self.dlq_topic,
                                json.dumps(event).encode("utf-8"),
                            )
                else:
                    import asyncio as _asyncio
                    await _asyncio.sleep(2 ** attempt)

    async def stop(self):
        await self._flush_clickhouse_batch()
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
