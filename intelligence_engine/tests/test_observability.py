import pytest
import asyncio
from unittest.mock import patch
from intelligence_engine.core.observability import trace, PROCESSING_LATENCY

def test_sync_trace_decorator():
    with patch('intelligence_engine.core.observability.PROCESSING_LATENCY.labels') as mock_labels:
        @trace("test_sync_op")
        def sync_func():
            return "ok"
            
        result = sync_func()
        assert result == "ok"
        mock_labels.assert_called_with(operation="test_sync_op")
        mock_labels.return_value.observe.assert_called_once()

@pytest.mark.asyncio
async def test_async_trace_decorator():
    with patch('intelligence_engine.core.observability.PROCESSING_LATENCY.labels') as mock_labels:
        @trace("test_async_op")
        async def async_func():
            await asyncio.sleep(0.01)
            return "async_ok"
            
        result = await async_func()
        assert result == "async_ok"
        mock_labels.assert_called_with(operation="test_async_op")
        mock_labels.return_value.observe.assert_called_once()
