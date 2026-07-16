import asyncio
import logging
from typing import List, Dict, Any
import clickhouse_connect

try:
    from kafka_consumer import route_to_dlq
except ImportError:
    try:
        from intelligence_engine.kafka_consumer import route_to_dlq
    except ImportError:
        def route_to_dlq(data, err):
            logging.error(f"[DLQ Fallback] {err}: {data}")

from intelligence_engine.core.observability import trace, CLICKHOUSE_LATENCY

logger = logging.getLogger(__name__)

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
            logger.info("Connected to ClickHouse")
        except Exception as e:
            logger.error(f"ClickHouse connection failed: {e}")

    async def write_batch(self, events: List[Dict[str, Any]]):
        async with self.lock:
            self.buffer.extend(events)
            should_flush = len(self.buffer) >= self.max_batch_size
        if should_flush:
            await self.flush()
            
    @trace("clickhouse_flush")
    async def flush(self):
        async with self.lock:
            if not self.buffer or not self.client:
                return
            to_flush = self.buffer.copy()
        
        try:
            logger.info(f"Flushing {len(to_flush)} events to ClickHouse")
            column_names = list(to_flush[0].keys())
            data = [[event.get(col) for col in column_names] for event in to_flush]
            import time
            start_time = time.time()
            self.client.insert('soc_events', data, column_names=column_names)
            duration = time.time() - start_time
            CLICKHOUSE_LATENCY.observe(duration)
            logger.info(f"Successfully flushed {len(to_flush)} events")
            
            async with self.lock:
                # Remove only the events we successfully flushed
                self.buffer = self.buffer[len(to_flush):]
                
        except Exception as e:
            logger.error(f"ClickHouse flush failed: {e}")
            async with self.lock:
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
