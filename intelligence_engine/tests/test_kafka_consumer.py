import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from intelligence_engine.kafka_consumer import process_batch_with_retry, route_to_dlq

@pytest.mark.asyncio
async def test_process_batch_with_retry_success():
    events = [{"event_id": "123", "data": "test"}]
    
    with patch('intelligence_engine.kafka_consumer._detection_engine') as mock_engine:
        # Mock successful extraction and detection
        mock_df = MagicMock()
        mock_df.empty = False
        mock_engine.extract_features.return_value = mock_df
        mock_engine.detect_anomalies.return_value = [1] # Normal
        
        result = await process_batch_with_retry(events)
        assert result == True
        mock_engine.extract_features.assert_called_once_with(events)
        mock_engine.detect_anomalies.assert_called_once_with(mock_df)

@pytest.mark.asyncio
async def test_process_batch_with_retry_failure_and_backoff():
    events = [{"event_id": "123"}]
    
    with patch('intelligence_engine.kafka_consumer._detection_engine') as mock_engine, \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        
        # Make extraction fail 2 times then succeed (empty DF = True)
        mock_engine.extract_features.side_effect = [Exception("error1"), Exception("error2"), MagicMock(empty=True)]
        
        result = await process_batch_with_retry(events, max_retries=3)
        
        assert result == True
        assert mock_engine.extract_features.call_count == 3
        # Should have slept 2 times with backoff
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

@pytest.mark.asyncio
async def test_process_batch_with_retry_exhaustion():
    events = [{"event_id": "123"}]
    
    with patch('intelligence_engine.kafka_consumer._detection_engine') as mock_engine, \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        
        mock_engine.extract_features.side_effect = Exception("persistent error")
        
        result = await process_batch_with_retry(events, max_retries=2)
        
        assert result == False
        assert mock_engine.extract_features.call_count == 3 # Initial + 2 retries
        assert mock_sleep.call_count == 2

def test_route_to_dlq():
    with patch('intelligence_engine.kafka_consumer.dlq_producer') as mock_producer, \
         patch('intelligence_engine.kafka_consumer.DLQ_EVENTS_COUNTER') as mock_counter:
        route_to_dlq({"test": "data"}, "test error")
        mock_producer.produce.assert_called_once()
        args, kwargs = mock_producer.produce.call_args
        assert args[0] == "soc_telemetry_dlq"
        assert b'"test": "data"' in kwargs["value"]
        assert b'"error": "test error"' in kwargs["value"]
        mock_counter.labels.assert_called_with(reason="dlq_route")
