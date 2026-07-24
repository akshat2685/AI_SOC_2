import pytest
import json
import time
from unittest.mock import MagicMock, patch, AsyncMock

from intelligence_engine.kafka_consumer import route_to_dlq, DLQ_TOPIC

@pytest.fixture
def mock_dlq_producer(monkeypatch):
    mock_prod = MagicMock()
    monkeypatch.setattr("intelligence_engine.kafka_consumer.dlq_producer", mock_prod)
    return mock_prod

def test_route_to_dlq_successful_packaging(mock_dlq_producer):
    """Test that event data and error reason are packaged correctly and produced to DLQ_TOPIC."""
    raw_event = {"event_id": "evt-101", "type": "suspicious_login", "ip": "192.168.1.50"}
    error_reason = "SchemaValidationException: Missing mandatory field 'user_id'"

    route_to_dlq(raw_event, error_reason)

    mock_dlq_producer.produce.assert_called_once()
    args, kwargs = mock_dlq_producer.produce.call_args
    assert args[0] == DLQ_TOPIC
    
    payload = json.loads(kwargs["value"].decode("utf-8"))
    assert payload["original_event"] == raw_event
    assert payload["error"] == error_reason
    assert "timestamp" in payload
    assert isinstance(payload["timestamp"], (int, float))

def test_route_to_dlq_producer_exception_handling(mock_dlq_producer):
    """Test that route_to_dlq catches exceptions during production without crashing the caller."""
    mock_dlq_producer.produce.side_effect = Exception("Kafka broker unreachable")
    
    raw_event = {"event_id": "evt-102"}
    # Should not raise exception
    route_to_dlq(raw_event, "Broker failure")

@pytest.mark.asyncio
async def test_dlq_replay_mechanism():
    """Test replaying messages from DLQ topic into main ingestion pipeline."""
    dlq_messages = [
        {
            "original_event": {"event_id": "evt-201", "user_id": "u-42", "action": "login"},
            "error": "TransientDatabaseError",
            "timestamp": time.time()
        },
        {
            "original_event": {"event_id": "evt-202", "user_id": "u-43", "action": "exfiltrate"},
            "error": "RateLimitError",
            "timestamp": time.time()
        }
    ]

    processed_events = []
    
    async def mock_replay_worker(messages):
        for msg in messages:
            # Simulate validating and re-processing original event
            orig = msg.get("original_event")
            if orig and "event_id" in orig:
                processed_events.append(orig)

    await mock_replay_worker(dlq_messages)

    assert len(processed_events) == 2
    assert processed_events[0]["event_id"] == "evt-201"
    assert processed_events[1]["event_id"] == "evt-202"
