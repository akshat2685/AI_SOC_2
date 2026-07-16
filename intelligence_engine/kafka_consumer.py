import os
import json
import asyncio
import logging
import uuid
import time
from confluent_kafka import Consumer, Producer, KafkaError, TopicPartition

from intelligence_engine.ml.detection_engine import AutonomousDetectionEngine
from intelligence_engine.agents.soc_orchestrator import run_orchestrator
from intelligence_engine.core.clickhouse_writer import ClickHouseWriter
from intelligence_engine.core.observability import trace, KAFKA_LAG_GAUGE, DLQ_EVENTS_COUNTER

logger = logging.getLogger(__name__)

KAFKA_BROKER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = "soc_telemetry"
DLQ_TOPIC = "soc_telemetry_dlq"

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASS = os.getenv("CLICKHOUSE_PASSWORD", "")

# Shared detection engine instance (trained on first batch)
_detection_engine = AutonomousDetectionEngine()
dlq_producer = Producer({'bootstrap.servers': KAFKA_BROKER})

clickhouse_writer = ClickHouseWriter(
    host=CLICKHOUSE_HOST, 
    port=CLICKHOUSE_PORT, 
    user=CLICKHOUSE_USER, 
    password=CLICKHOUSE_PASS
)

_watermarks_cache = {}

def route_to_dlq(event_data, error_msg):
    try:
        dlq_event = {
            "original_event": event_data,
            "error": error_msg,
            "timestamp": time.time()
        }
        dlq_producer.produce(DLQ_TOPIC, value=json.dumps(dlq_event).encode('utf-8'))
        dlq_producer.poll(0)
        DLQ_EVENTS_COUNTER.labels(reason="dlq_route").inc()
    except Exception as e:
        logger.error("[DLQ] Failed to route to DLQ: %s", e)

async def watermark_updater_task():
    """Task 12: Optimize Kafka watermarks by caching them via a background updater, removing blocking network calls from the loop."""
    conf = {'bootstrap.servers': KAFKA_BROKER}
    try:
        w_consumer = Consumer(conf)
        while True:
            try:
                metadata = await asyncio.to_thread(w_consumer.list_topics, TOPIC, timeout=2.0)
                if TOPIC in metadata.topics:
                    for p_id in metadata.topics[TOPIC].partitions.keys():
                        tp = TopicPartition(TOPIC, p_id)
                        low, high = await asyncio.to_thread(w_consumer.get_watermark_offsets, tp, timeout=1.0, cached=False)
                        _watermarks_cache[p_id] = high
            except Exception as e:
                pass
            await asyncio.sleep(2.0)
    except Exception as e:
        logger.error("[Watermark Updater] Failed: %s", str(e))
    finally:
        if 'w_consumer' in locals():
            w_consumer.close()

@trace("process_batch")
async def process_batch_with_retry(events_batch, max_retries=3):
    retries = 0
    backoff = 1.0
    while retries <= max_retries:
        try:
            if not events_batch:
                return True
                
            # 1. Feature Extraction
            features_df = _detection_engine.extract_features(events_batch)
            if features_df.empty:
                logger.warning("[Pipeline] Feature extraction returned empty DF - skipping")
                return True

            # 2. Anomaly Detection (Isolation Forest)
            predictions = _detection_engine.detect_anomalies(features_df)

            # 3. If anomaly detected (-1), trigger SOC orchestrator concurrently
            orchestrator_tasks = []
            for idx, label in enumerate(predictions):
                if label == -1:
                    alert_id = events_batch[idx].get("event_id", str(uuid.uuid4()))
                    logger.warning(
                        "[ANOMALY] Event %s flagged by Isolation Forest - launching SOC orchestrator",
                        alert_id,
                    )
                    orchestrator_tasks.append(run_orchestrator(alert_id=alert_id, hitl_level=1))
            
            if orchestrator_tasks:
                results = await asyncio.gather(*orchestrator_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        logger.error("[SOC Orchestrator Error]: %s", str(res))

            return True
        except Exception as e:
            retries += 1
            if retries > max_retries:
                logger.error("[Processing Error] Max retries reached for batch. Error: %s", str(e))
                return False
            logger.warning("[Processing Error] Retrying batch due to error: %s. Retry %d/%d. Backoff %f s", str(e), retries, max_retries, backoff)
            await asyncio.sleep(backoff)
            backoff *= 2

    return False

async def dlq_consumer_task():
    conf = {
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'intelligence_engine_dlq_group',
        'auto.offset.reset': 'earliest'
    }
    try:
        consumer = Consumer(conf)
        consumer.subscribe([DLQ_TOPIC])
        logger.info("[DLQ Consumer] Subscribed to topic: %s", DLQ_TOPIC)
        while True:
            await asyncio.sleep(1.0)
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    logger.error("[DLQ Kafka Error] %s", msg.error())
                    continue
            
            try:
                raw_data = msg.value().decode('utf-8')
                event = json.loads(raw_data)
                logger.critical("[DLQ ALERT] Dead letter event detected! Error: %s", event.get('error', 'unknown'))
                # Additional alerting logic could be implemented here
            except Exception as e:
                logger.error("[DLQ Processing Error] %s", str(e))
    except Exception as e:
        logger.error("[DLQ Consumer] Initialization failed: %s", str(e))
    finally:
        if 'consumer' in locals():
            consumer.close()

async def consume_events():
    conf = {
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'intelligence_engine_group',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False
    }

    batch_size = 10
    max_batch_size = 100
    min_batch_size = 1
    
    # Task 7: Connect to ClickHouse for persistence
    clickhouse_writer.connect()
    
    # Start background tasks
    asyncio.create_task(clickhouse_writer.batch_loop())
    asyncio.create_task(watermark_updater_task())
    
    try:
        consumer = Consumer(conf)
        consumer.subscribe([TOPIC])
        logger.info("[Intelligence Engine] Subscribed to Kafka topic: %s", TOPIC)

        while True:
            await asyncio.sleep(0.1)
            
            # Back-Pressure: Consumer lag monitoring
            lag_sum = 0
            try:
                partitions = consumer.assignment()
                # Get current positions
                positions = consumer.position(partitions)
                for p in positions:
                    if p.partition in _watermarks_cache and p.offset > 0:
                        high = _watermarks_cache[p.partition]
                        lag = max(0, high - p.offset)
                        lag_sum += lag
                        KAFKA_LAG_GAUGE.labels(partition=str(p.partition)).set(lag)
            except Exception as e:
                pass
            
            # Back-Pressure: Dynamic batch sizing based on consumer lag
            if lag_sum > 1000:
                batch_size = min(max_batch_size, batch_size * 2)
            elif lag_sum < 100:
                batch_size = max(min_batch_size, batch_size // 2)

            messages = consumer.consume(num_messages=batch_size, timeout=1.0)
            if not messages:
                continue
            
            # Task 9: partition-aware batches
            partition_batches = {}
            for msg in messages:
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error("[Kafka Error] %s", msg.error())
                        continue

                raw_data = None
                try:
                    raw_data = msg.value().decode('utf-8')
                    event = json.loads(raw_data)
                    
                    p_id = msg.partition()
                    partition_batches.setdefault(p_id, []).append(event)

                except Exception as e:
                    logger.error("[Processing Error] Failed to parse message: %s", str(e))
                    if raw_data is not None:
                        route_to_dlq(raw_data, f"JSON parse or unhandled error: {str(e)}")
            
            all_events = [ev for batch in partition_batches.values() for ev in batch]
            if not all_events:
                consumer.commit(asynchronous=True)
                continue
                
            # Task 7: Persist raw telemetry to ClickHouse BEFORE feature extraction
            await clickhouse_writer.write_batch(all_events)
            
            # Task 9: Async worker pool (concurrently processing partition batches)
            worker_tasks = []
            for p_id, batch in partition_batches.items():
                worker_tasks.append(asyncio.create_task(process_batch_with_retry(batch)))
                
            results = await asyncio.gather(*worker_tasks, return_exceptions=True)
            for p_idx, res in enumerate(results):
                if isinstance(res, Exception) or not res:
                    # Retrieve the batch that failed to route to DLQ
                    failed_batch = list(partition_batches.values())[p_idx]
                    for ev in failed_batch:
                        route_to_dlq(ev, f"Batch processing failed: {str(res)}")
                        
            # Commit offsets after batch is processed
            consumer.commit(asynchronous=True)

    except Exception as e:
        logger.error("[Kafka Consumer] Initialization failed: %s. Retrying...", str(e))
    finally:
        if 'consumer' in locals():
            consumer.close()
