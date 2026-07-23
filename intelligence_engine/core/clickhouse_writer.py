import asyncio
from typing import List, Dict, Any
import clickhouse_connect
import structlog

try:
    from kafka_consumer import route_to_dlq
except ImportError:
    try:
        from intelligence_engine.kafka_consumer import route_to_dlq
    except ImportError:
        def route_to_dlq(data, err):
            logger = structlog.get_logger(__name__)
            logger.error("dlq_fallback", error=err, data=data)

from intelligence_engine.core.observability import trace, CLICKHOUSE_LATENCY

logger = structlog.get_logger(__name__)

class ClickHouseWriter:
    def __init__(self, host: str, port: int, user: str = 'default', password: str = ''):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.client = None
        self.buffer = []
        self.max_batch_size = 1000
        self.lock = asyncio.Lock()
        
    def connect(self):
        try:
            self.client = clickhouse_connect.get_client(
                host=self.host, port=self.port, username=self.user, password=self.password
            )
            logger.info("clickhouse_connected", host=self.host, port=self.port)
        except Exception as e:
            logger.error("clickhouse_connection_failed", host=self.host, port=self.port, error=str(e), exc_info=True)

    async def write_batch(self, events: List[Dict[str, Any]]):
        async with self.lock:
            self.buffer.extend(events)
            if len(self.buffer) >= self.max_batch_size:
                await self._flush_unlocked()
            
    @trace("clickhouse_flush")
    async def flush(self):
        async with self.lock:
            await self._flush_unlocked()

    async def _flush_unlocked(self):
        """Internal flush execution under lock."""
        if not self.buffer or not self.client:
            return
        
        to_flush = self.buffer.copy()
        
        try:
            logger.info("clickhouse_flush_started", event_count=len(to_flush))
            column_names = list(to_flush[0].keys())
            data = [[event.get(col) for col in column_names] for event in to_flush]
            import time
            start_time = time.time()
            
            # Execute blocking insert call in thread pool to prevent blocking main event loop
            await asyncio.to_thread(self.client.insert, 'soc_events', data, column_names=column_names)
            
            duration = time.time() - start_time
            CLICKHOUSE_LATENCY.observe(duration)
            logger.info("clickhouse_flush_completed", event_count=len(to_flush), duration_seconds=round(duration, 3))
            
            # Remove only the events we successfully flushed
            self.buffer = self.buffer[len(to_flush):]
                
        except Exception as e:
            logger.error("clickhouse_flush_failed", error=str(e), event_count=len(to_flush), exc_info=True)
            failed_events = self.buffer[:len(to_flush)]
            # Still clear the failed events from buffer to prevent memory leak
            self.buffer = self.buffer[len(to_flush):]
            
            # Send to DLQ
            for event in failed_events:
                route_to_dlq(event, f"ClickHouse insert failed: {str(e)}")

    def query(self, sql: str) -> Any:
        if self.client:
            return self.client.query(sql).result_rows
        return []
        
    def get_time_series_analytics(self) -> List[Dict[str, Any]]:
        # Example analytical query: events per minute
        sql = """
        SELECT toStartOfMinute(timestamp) AS time, count() AS event_count, event_type
        FROM soc_events
        WHERE timestamp >= now() - INTERVAL 1 HOUR
        GROUP BY time, event_type
        ORDER BY time ASC
        """
        if self.client:
            result = self.client.query(sql)
            return [dict(zip(result.column_names, row)) for row in result.result_rows]
        return []
        
    async def batch_loop(self):
        while True:
            await asyncio.sleep(5)
            await self.flush()
