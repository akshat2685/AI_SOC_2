"""
Dead-Letter Queue routing & replay tests (audit C — real Kafka event bus + DLQ).

Verifies that when the primary Kafka publish fails, the message is not silently
dropped but routed to the configured DLQ topic with enough metadata to replay it,
and that a replay re-publishes the original message to its original topic.

The aiokafka producer is replaced with an in-memory fake so these tests run on
every platform without a live Kafka broker.
"""
import json
from typing import Any, Dict, List, Tuple

import pytest

from backend.app.infrastructure.event_bus import KafkaEventBus


class _FakeProducer:
    """
    Records every (topic, payload) sent. Fails on topics listed in
    `fail_topics` so we can drive messages into the DLQ deterministically.
    """

    def __init__(self, fail_topics: set):
        self.fail_topics = fail_topics
        self.sent: List[Tuple[str, bytes]] = []

    async def send_and_wait(self, topic: str, payload: bytes):
        if topic in self.fail_topics:
            raise RuntimeError(f"broker rejected publish to {topic}")
        self.sent.append((topic, payload))
        return None


def _make_bus(fail_topics: set) -> Tuple[KafkaEventBus, _FakeProducer]:
    bus = KafkaEventBus()
    producer = _FakeProducer(fail_topics)
    bus._producer = producer  # inject fake in place of aiokafka producer
    return bus, producer


@pytest.mark.asyncio
async def test_failed_publish_routes_to_dlq():
    bus, producer = _make_bus(fail_topics={"soc_alerts"})
    message = {"alert_id": "a-123", "severity": "high"}

    await bus._publish_async("soc_alerts", message)

    # Nothing landed on the primary topic; exactly one DLQ record was written.
    assert all(topic != "soc_alerts" for topic, _ in producer.sent)
    dlq_records = [json.loads(p) for t, p in producer.sent if t == bus._dlq_topic]
    assert len(dlq_records) == 1

    record = dlq_records[0]
    assert record["original_topic"] == "soc_alerts"
    assert record["message"] == message
    assert "error" in record  # failure reason preserved for triage
    assert bus._failure_count == 1


@pytest.mark.asyncio
async def test_dlq_message_can_be_replayed_to_original_topic():
    # 1. First attempt fails → message parked in DLQ.
    bus, producer = _make_bus(fail_topics={"soc_alerts"})
    message = {"alert_id": "a-456", "severity": "critical"}
    await bus._publish_async("soc_alerts", message)

    dlq_payload = next(p for t, p in producer.sent if t == bus._dlq_topic)
    parked = json.loads(dlq_payload)

    # 2. Broker recovers; replay the parked message to its original topic.
    producer.fail_topics = set()
    await bus._publish_async(parked["original_topic"], parked["message"])

    replayed = [json.loads(p) for t, p in producer.sent if t == "soc_alerts"]
    assert replayed == [message]  # exactly-once replay of the original payload


@pytest.mark.asyncio
async def test_healthy_publish_never_touches_dlq():
    bus, producer = _make_bus(fail_topics=set())
    await bus._publish_async("soc_alerts", {"alert_id": "a-789"})

    assert [t for t, _ in producer.sent] == ["soc_alerts"]
    assert bus._failure_count == 0
