import pytest
import asyncio
import logging
from unittest.mock import patch, MagicMock, AsyncMock
from intelligence_engine.core.observability import (
    trace, PROCESSING_LATENCY, setup_opentelemetry, 
    setup_json_logging, CustomJsonFormatter, trace_ai_action, metrics_worker
)

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

def test_setup_opentelemetry():
    with patch('intelligence_engine.core.observability.otel_trace') as mock_otel_trace, \
         patch('intelligence_engine.core.observability.TracerProvider') as mock_provider, \
         patch('intelligence_engine.core.observability.BatchSpanProcessor') as mock_bsp, \
         patch('intelligence_engine.core.observability.ConsoleSpanExporter') as mock_cse, \
         patch('os.environ.get', return_value="1"), \
         patch('os.getenv', side_effect=lambda k: "1" if k == "DEBUG_SPANS" else None):
        setup_opentelemetry()
        mock_otel_trace.set_tracer_provider.assert_called_once()
        mock_otel_trace.get_tracer_provider.return_value.add_span_processor.assert_called_once()

def test_setup_json_logging():
    with patch('logging.getLogger') as mock_get_logger:
        mock_root_logger = MagicMock()
        mock_get_logger.return_value = mock_root_logger
        mock_root_logger.handlers = [MagicMock()]
        
        setup_json_logging()
        
        mock_root_logger.setLevel.assert_called_with(logging.INFO)
        mock_root_logger.removeHandler.assert_called_once()
        mock_root_logger.addHandler.assert_called_once()
        
def test_custom_json_formatter():
    formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    log_record = {}
    record = logging.LogRecord("name", logging.INFO, "pathname", 1, "msg", (), None)
    
    with patch('intelligence_engine.core.observability.otel_trace.get_current_span') as mock_get_span:
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        mock_span.get_span_context.return_value.trace_id = 12345
        mock_span.get_span_context.return_value.span_id = 67890
        mock_get_span.return_value = mock_span
        
        formatter.add_fields(log_record, record, {})
        
        assert log_record['trace_id'] == format(12345, '032x')
        assert log_record['span_id'] == format(67890, '016x')

def test_trace_ai_action_sync():
    with patch('intelligence_engine.core.observability.tracer') as mock_tracer:
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        
        @trace_ai_action("test_action")
        def sync_action():
            return "success"
            
        result = sync_action()
        assert result == "success"
        mock_span.set_attribute.assert_called_with("action.status", "success")

@pytest.mark.asyncio
async def test_trace_ai_action_async():
    with patch('intelligence_engine.core.observability.tracer') as mock_tracer:
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
        
        @trace_ai_action("test_async_action")
        async def async_action():
            return "async_success"
            
        result = await async_action()
        assert result == "async_success"
        mock_span.set_attribute.assert_called_with("action.status", "success")

@pytest.mark.asyncio
async def test_metrics_worker():
    with patch('intelligence_engine.core.observability.psutil.Process') as mock_process, \
         patch('intelligence_engine.core.observability.logging.getLogger') as mock_get_logger, \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        
        mock_p = MagicMock()
        mock_process.return_value = mock_p
        mock_p.memory_info.return_value.rss = 100 * 1024 * 1024 # 100MB
        mock_p.cpu_percent.return_value = 0.5
        
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        mock_sleep.side_effect = Exception("Stop loop")
        
        with pytest.raises(Exception, match="Stop loop"):
            await metrics_worker()
            
        mock_logger.info.assert_called_once()
