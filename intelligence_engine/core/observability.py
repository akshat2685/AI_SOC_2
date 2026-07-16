import functools
import logging
import time
import asyncio

from prometheus_client import Gauge, Histogram, Counter

try:
    from opentelemetry import trace as otel_trace
    tracer = otel_trace.get_tracer(__name__)
except ImportError:
    tracer = None

logger = logging.getLogger(__name__)

# Prometheus Metrics
KAFKA_LAG_GAUGE = Gauge("kafka_consumer_lag", "Current lag of the Kafka consumer", ["partition"])
PROCESSING_LATENCY = Histogram("event_processing_latency_seconds", "Latency of processing events", ["operation"])
CLICKHOUSE_LATENCY = Histogram("clickhouse_insert_latency_seconds", "Latency of ClickHouse inserts")
DLQ_EVENTS_COUNTER = Counter("dlq_events_total", "Total events sent to DLQ", ["reason"])

def trace(operation_name: str):
    """Decorator for Jaeger tracing (via OpenTelemetry) and Prometheus metrics."""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
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
