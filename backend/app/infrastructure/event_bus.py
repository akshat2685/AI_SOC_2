import json
import logging
from typing import Dict, Any, Callable, List

# Adhering to Dependency Inversion Principle, implement the interface defined in application layer.
from application.services import IEventBus

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class StubKafkaEventBus(IEventBus):
    """
    Kafka-based event bus stub implementation.
    """
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}

    def publish(self, topic: str, message: Dict[str, Any]) -> None:
        logger.info(f"[Kafka Stub] Publishing to '{topic}': {json.dumps(message)}")
        if topic in self._subscribers:
            for handler in self._subscribers[topic]:
                try:
                    handler(message)
                except Exception as e:
                    logger.error(f"Error handling message on topic {topic}: {e}")

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)
        logger.info(f"[Kafka Stub] Subscribed handler to '{topic}'")

class StubRedisEventBus(IEventBus):
    """
    Redis PubSub event bus stub implementation.
    """
    def publish(self, topic: str, message: Dict[str, Any]) -> None:
        logger.info(f"[Redis Stub] Publishing to '{topic}': {json.dumps(message)}")

    def subscribe(self, topic: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        logger.info(f"[Redis Stub] Subscribed handler to '{topic}'")
