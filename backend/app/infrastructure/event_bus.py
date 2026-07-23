import json
import structlog
from typing import Dict, Any, Callable, List

# Adhering to Dependency Inversion Principle, implement the interface defined in application layer.
from application.services import IEventBus

logger = structlog.get_logger(__name__)

class StubKafkaEventBus(IEventBus):
    """
    Kafka-based event bus stub implementation.
    """
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
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
        logger.info("kafka_stub_subscribe", topic=topic)

class StubRedisEventBus(IEventBus):
    """
    Redis PubSub event bus stub implementation.
    """
    def publish(self, topic: str, message: Dict[str, Any]) -> None:
        logger.info("redis_stub_publish", topic=topic)

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        logger.info("redis_stub_subscribe", topic=topic)
