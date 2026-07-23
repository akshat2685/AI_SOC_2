import functools
import structlog
import time
import asyncio

from prometheus_client import Gauge, Histogram, Counter

try:
    from opentelemetry import trace as otel_trace
    tracer = otel_trace.get_tracer(__name__)
except ImportError:
    tracer = None

logger = structlog.get_logger(__name__)

# Prometheus Metrics
KAFKA_LAG_GAUGE = Gauge("kafka_consumer_lag", "Current lag of the Kafka consumer", ["partition"])
PROCESSING_LATENCY = Histogram("event_processing_latency_seconds", "Latency of processing events", ["operation"])
CLICKHOUSE_LATENCY = Histogram("clickhouse_insert_latency_seconds", "Latency of ClickHouse inserts")
DLQ_EVENTS_COUNTER = Counter("dlq_events_total", "Total events sent to DLQ", ["reason"])

def trace(operation_name: str):
    """Decorator for Jaeger tracing (via OpenTelemetry) and Prometheus metrics."""
    def decorator(func):
        import inspect
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                logger.debug(f"Trace started: {operation_name} [func: {func.__name__}]")
                span = tracer.start_span(operation_name) if tracer else None
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Trace error: {operation_name} - {str(e)}")
                    if span:
                        span.record_exception(e)
                        span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR))
                    raise
                finally:
                    duration = time.time() - start_time
                    PROCESSING_LATENCY.labels(operation=operation_name).observe(duration)
                    logger.debug(f"Trace finished: {operation_name} [duration: {duration:.4f}s]")
                    if span:
                        span.end()
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                logger.debug(f"Trace started: {operation_name} [func: {func.__name__}]")
                span = tracer.start_span(operation_name) if tracer else None
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Trace error: {operation_name} - {str(e)}")
                    if span:
                        span.record_exception(e)
                        span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR))
                    raise
                finally:
                    duration = time.time() - start_time
                    PROCESSING_LATENCY.labels(operation=operation_name).observe(duration)
                    logger.debug(f"Trace finished: {operation_name} [duration: {duration:.4f}s]")
                    if span:
                        span.end()
            return sync_wrapper
    return decorator

import json
import psutil
from pythonjsonlogger import jsonlogger
from opentelemetry import trace as otel_trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
import os

def setup_opentelemetry():
    resource = Resource.create({"service.name": "edysor-x-intelligence-engine"})
    otel_trace.set_tracer_provider(TracerProvider(resource=resource))
    tracer_provider = otel_trace.get_tracer_provider()
    
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except ImportError:
            pass
    elif os.getenv("DEBUG_SPANS") == "1":
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        
    # Also initialize tracer
    global tracer
    tracer = otel_trace.get_tracer(__name__)

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        current_span = otel_trace.get_current_span()
        if current_span and current_span.is_recording():
            log_record['trace_id'] = format(current_span.get_span_context().trace_id, '032x')
            log_record['span_id'] = format(current_span.get_span_context().span_id, '016x')

def setup_json_logging():
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    logHandler = logging.StreamHandler()
    formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    logHandler.setFormatter(formatter)
    root_logger.addHandler(logHandler)

def trace_ai_action(action_name: str):
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not tracer:
                    return await func(*args, **kwargs)
                with tracer.start_as_current_span(action_name) as span:
                    try:
                        result = await func(*args, **kwargs)
                        span.set_attribute("action.status", "success")
                        return result
                    except Exception as e:
                        span.set_attribute("action.status", "error")
                        span.record_exception(e)
                        raise
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not tracer:
                    return func(*args, **kwargs)
                with tracer.start_as_current_span(action_name) as span:
                    try:
                        result = func(*args, **kwargs)
                        span.set_attribute("action.status", "success")
                        return result
                    except Exception as e:
                        span.set_attribute("action.status", "error")
                        span.record_exception(e)
                        raise
            return sync_wrapper
    return decorator

async def metrics_worker():
    process = psutil.Process()
    metrics_logger = structlog.get_logger("metrics_worker")
    while True:
        try:
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / (1024 * 1024)
            cpu_percent = process.cpu_percent(interval=None)
            if mem_mb > 1024 or cpu_percent > 80.0:
                metrics_logger.warning(
                    f"Resource Limits Exceeded: RAM={mem_mb:.2f}MB, CPU={cpu_percent:.2f}%", 
                    extra={"memory_mb": mem_mb, "cpu_percent": cpu_percent}
                )
            else:
                metrics_logger.info(
                    f"Resource Check: RAM={mem_mb:.2f}MB, CPU={cpu_percent:.2f}%", 
                    extra={"memory_mb": mem_mb, "cpu_percent": cpu_percent}
                )
        except Exception as e:
            metrics_logger.error(f"Error collecting metrics: {e}")
        await asyncio.sleep(60)
