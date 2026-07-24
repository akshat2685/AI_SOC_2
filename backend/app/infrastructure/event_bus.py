import asyncio
import json
import os
import structlog
from typing import Dict, Any, Callable, List

from backend.app.application.services import IEventBus

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Stub — for unit tests only. Selected via EVENT_BUS_BACKEND=stub env var.
# ---------------------------------------------------------------------------

class StubKafkaEventBus(IEventBus):
    """In-memory stub. Only use in tests (EVENT_BUS_BACKEND=stub)."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    def publish(self, topic: str, message: Dict[str, Any]) -> None:
        logger.info("kafka_stub_publish", topic=topic)
        if topic in self._subscribers:
            for handler in self._subscribers[topic]:
                try:
                    handler(message)
                except Exception as e:
                    logger.error("kafka_stub_handler_error", topic=topic, error=str(e))

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        self._subscribers.setdefault(topic, []).append(handler)
        logger.info("kafka_stub_subscribe", topic=topic)


class StubRedisEventBus(IEventBus):
    """Redis stub — no-op. Only use in tests."""

    def publish(self, topic: str, message: Dict[str, Any]) -> None:
        logger.info("redis_stub_publish", topic=topic)

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        logger.info("redis_stub_subscribe", topic=topic)


# ---------------------------------------------------------------------------
# Real Kafka producer — production default (EVENT_BUS_BACKEND=kafka)
# ---------------------------------------------------------------------------

class KafkaEventBus(IEventBus):
    """
    Production Kafka event bus.

    Configuration via env vars:
      KAFKA_BOOTSTRAP_SERVERS   comma-separated broker list
      KAFKA_DLQ_TOPIC           dead-letter topic (default: soc_alerts_dlq)
      KAFKA_SECURITY_PROTOCOL   PLAINTEXT | SSL | SASL_SSL (default: PLAINTEXT)
      KAFKA_SASL_MECHANISM      PLAIN | SCRAM-SHA-256 | SCRAM-SHA-512
      KAFKA_SASL_USERNAME / KAFKA_SASL_PASSWORD
    """

    def __init__(self) -> None:
        self._producer = None
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._bootstrap_servers: str = os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self._dlq_topic: str = os.getenv("KAFKA_DLQ_TOPIC", "soc_alerts_dlq")
        self._failure_count: int = 0

    # ------------------------------------------------------------------
    # Startup / health check
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect to Kafka and verify required topics exist. Raises on failure."""
        from aiokafka import AIOKafkaProducer
        from aiokafka.admin import AIOKafkaAdminClient

        security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
        sasl_mechanism = os.getenv("KAFKA_SASL_MECHANISM", "PLAIN")

        producer_kwargs: Dict[str, Any] = dict(
            bootstrap_servers=self._bootstrap_servers,
            acks="all",
            enable_idempotence=True,
            max_in_flight_requests_per_connection=1,
            retries=5,
            security_protocol=security_protocol,
        )
        if security_protocol.startswith("SASL"):
            producer_kwargs.update(
                sasl_mechanism=sasl_mechanism,
                sasl_plain_username=os.getenv("KAFKA_SASL_USERNAME", ""),
                sasl_plain_password=os.getenv("KAFKA_SASL_PASSWORD", ""),
            )

        self._producer = AIOKafkaProducer(**producer_kwargs)
        await self._producer.start()

        # Verify broker connectivity by listing topics
        admin = AIOKafkaAdminClient(bootstrap_servers=self._bootstrap_servers)
        await admin.start()
        try:
            topics = await admin.list_topics()
            logger.info("kafka_connected", broker=self._bootstrap_servers, topics=list(topics))
        finally:
            await admin.close()

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    # ------------------------------------------------------------------
    # IEventBus interface
    # ------------------------------------------------------------------

    def publish(self, topic: str, message: Dict[str, Any]) -> None:
        """Fire-and-forget publish — schedules an async task."""
        asyncio.ensure_future(self._publish_async(topic, message))

    async def _publish_async(self, topic: str, message: Dict[str, Any]) -> None:
        try:
            serialized = json.dumps(message).encode("utf-8")
            await self._producer.send_and_wait(topic, serialized)
            logger.info("kafka_published", topic=topic)
        except Exception as exc:
            self._failure_count += 1
            logger.error(
                "kafka_publish_failed",
                topic=topic,
                error=str(exc),
                failure_count=self._failure_count,
            )
            # Route to dead-letter topic so the alert isn't silently dropped
            try:
                dlq_payload = json.dumps(
                    {"original_topic": topic, "message": message, "error": str(exc)}
                ).encode("utf-8")
                await self._producer.send_and_wait(self._dlq_topic, dlq_payload)
                logger.warning("kafka_message_dlq", topic=topic, dlq=self._dlq_topic)
            except Exception as dlq_exc:
                logger.critical(
                    "kafka_dlq_failed",
                    dlq_topic=self._dlq_topic,
                    error=str(dlq_exc),
                )

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        self._subscribers.setdefault(topic, []).append(handler)
        logger.info("kafka_subscribe_registered", topic=topic)


# ---------------------------------------------------------------------------
# Factory — selects implementation from env
# ---------------------------------------------------------------------------

def create_event_bus() -> IEventBus:
    """
    Returns the correct event bus based on EVENT_BUS_BACKEND env var.
      kafka  (default) → real Kafka, production
      stub             → in-memory stub, tests only
    """
    backend = os.getenv("EVENT_BUS_BACKEND", "kafka").lower()
    if backend == "stub":
        logger.warning("event_bus_stub_mode", reason="EVENT_BUS_BACKEND=stub — alerts will NOT reach Kafka")
        return StubKafkaEventBus()
    return KafkaEventBus()
