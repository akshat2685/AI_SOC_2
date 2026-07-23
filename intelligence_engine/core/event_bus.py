import json
import asyncio
from abc import ABC, abstractmethod
from typing import Callable, Any
import structlog
from confluent_kafka import Producer, Consumer
from .config import get_settings

logger = structlog.get_logger(__name__)

class EventBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, event: dict) -> None: ...
    
    @abstractmethod
    async def subscribe(self, topic: str, handler: Callable) -> None: ...
    
    @abstractmethod
    async def start(self) -> None: ...
    
    @abstractmethod
    async def stop(self) -> None: ...

class KafkaEventBus(EventBus):
    def __init__(self):
        self.settings = get_settings()
        self.producer = Producer({'bootstrap.servers': self.settings.kafka.bootstrap_servers})
        self.consumer = Consumer({
            'bootstrap.servers': self.settings.kafka.bootstrap_servers,
            'group.id': 'soc_event_bus',
            'auto.offset.reset': 'earliest'
        })
        self.handlers = {}
        self.running = False

    async def publish(self, topic: str, event: dict) -> None:
        try:
            self.producer.produce(topic, json.dumps(event).encode('utf-8'))
            self.producer.poll(0)
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")

    async def subscribe(self, topic: str, handler: Callable) -> None:
        self.handlers[topic] = handler
        self.consumer.subscribe(list(self.handlers.keys()))

    async def start(self) -> None:
        self.running = True
        try:
            async with asyncio.TaskGroup() as tg:
                while self.running:
                    msg = self.consumer.poll(timeout=0.1)
                    await asyncio.sleep(0) # yield
                    if msg is None:
                        continue
                    if msg.error():
                        logger.error(f"Kafka error: {msg.error()}")
                        continue
                    topic = msg.topic()
                    if topic in self.handlers:
                        try:
                            data = json.loads(msg.value().decode('utf-8'))
                            handler = self.handlers[topic]
                            if asyncio.iscoroutinefunction(handler):
                                tg.create_task(handler(data))
                            else:
                                handler(data)
                        except Exception as e:
                            logger.error(f"Error handling message on {topic}: {e}")
        except Exception as e:
            logger.error(f"KafkaEventBus error: {e}")

    async def stop(self) -> None:
        self.running = False
        self.producer.flush()
        self.consumer.close()

class InMemoryEventBus(EventBus):
    def __init__(self):
        self.queues = {}
        self.handlers = {}
        self.running = False
        self.lock = asyncio.Lock()

    async def publish(self, topic: str, event: dict) -> None:
        async with self.lock:
            if topic not in self.queues:
                self.queues[topic] = asyncio.Queue()
        await self.queues[topic].put(event)

    async def subscribe(self, topic: str, handler: Callable) -> None:
        async with self.lock:
            self.handlers[topic] = handler
            if topic not in self.queues:
                self.queues[topic] = asyncio.Queue()

    async def start(self) -> None:
        self.running = True
        try:
            async with asyncio.TaskGroup() as tg:
                while self.running:
                    async with self.lock:
                        topics_queues = list(self.queues.items())
                    
                    for topic, queue in topics_queues:
                        try:
                            event = queue.get_nowait()
                            async with self.lock:
                                handler = self.handlers.get(topic)
                            if handler:
                                if asyncio.iscoroutinefunction(handler):
                                    tg.create_task(handler(event))
                                else:
                                    handler(event)
                        except asyncio.QueueEmpty:
                            pass
                    await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"InMemoryEventBus error: {e}")

    async def stop(self) -> None:
        self.running = False

def create_event_bus(backend='kafka') -> EventBus:
    if backend == 'kafka':
        return KafkaEventBus()
    return InMemoryEventBus()
