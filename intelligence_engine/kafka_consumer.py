import os
import json
import asyncio
import uuid
import time
from typing import Dict, Any, List, Optional
from confluent_kafka import Consumer, Producer, KafkaError, TopicPartition
import structlog

from intelligence_engine.ml.detection_engine import AutonomousDetectionEngine
from intelligence_engine.agents.soc_orchestrator import run_orchestrator
from intelligence_engine.core.clickhouse_writer import ClickHouseWriter
from intelligence_engine.core.observability import trace, KAFKA_LAG_GAUGE, DLQ_EVENTS_COUNTER
from intelligence_engine.core.notification_router import router as notification_router

logger = structlog.get_logger(__name__)

KAFKA_BROKER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = "soc_telemetry"
DLQ_TOPIC = "soc_telemetry_dlq"

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASS = os.getenv("CLICKHOUSE_PASSWORD", "")

_detection_engine = AutonomousDetectionEngine()
dlq_producer = Producer({'bootstrap.servers': KAFKA_BROKER})

clickhouse_writer = ClickHouseWriter(
    host=CLICKHOUSE_HOST, 
    port=CLICKHOUSE_PORT, 
    user=CLICKHOUSE_USER, 
    password=CLICKHOUSE_PASS
)

_watermarks_cache: Dict[int, int] = {}

def route_to_dlq(event_data: Any, error_msg: str) -> None:
    try:
        dlq_event = {
            "original_event": event_data,
            "error": error_msg,
            "timestamp": time.time()
        }
        dlq_producer.produce(DLQ_TOPIC, value=json.dumps(dlq_event).encode('utf-8'))
        dlq_producer.poll(0)
        DLQ_EVENTS_COUNTER.labels(reason="dlq_route").inc()
        logger.info("dlq_event_routed", topic=DLQ_TOPIC, error=error_msg)
    except Exception as e:
        logger.error("dlq_routing_failed", error=str(e), exc_info=True)

async def watermark_updater_task() -> None:
    """Task 12: Cache Kafka watermarks in background updater to remove blocking network calls."""
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
                logger.error(
                    "watermark_updater_failed",
                    error=str(e),
                    exc_info=True
                )
            await asyncio.sleep(2.0)
    except Exception as e:
        logger.error("watermark_updater_task_failed", error=str(e), exc_info=True)
    finally:
        if 'w_consumer' in locals():
            w_consumer.close()

@trace("process_batch")
async def process_batch_with_retry(events_batch: List[Dict[str, Any]], max_retries: int = 3) -> bool:
    retries = 0
    backoff = 1.0
    batch_size = len(events_batch)
    logger.info("process_batch_started", batch_size=batch_size)
    
    while retries <= max_retries:
        try:
            if not events_batch:
                return True
                
            features_df = _detection_engine.extract_features(events_batch)
            if features_df.empty:
                logger.warning("pipeline_feature_extraction_empty", batch_size=batch_size)
                return True

            predictions = _detection_engine.detect_anomalies(features_df)

            orchestrator_tasks = []
            orchestrator_meta = []
            for idx, label in enumerate(predictions):
                if label == -1:
                    event_data = events_batch[idx]
                    alert_id = event_data.get("event_id", str(uuid.uuid4()))
                    tenant_id = event_data.get("tenant_id", 1)
                    
                    logger.warning(
                        "anomaly_flagged_by_detection",
                        alert_id=alert_id,
                        tenant_id=tenant_id
                    )
                    
                    asyncio.create_task(notification_router.route(
                        tenant_id=int(tenant_id),
                        event_type="anomaly_detected",
                        payload={"alert_id": alert_id, **event_data}
                    ))
                    
                    orchestrator_tasks.append(run_orchestrator(alert_id=alert_id, hitl_level=1))
                    orchestrator_meta.append({"tenant_id": tenant_id, "alert_id": alert_id})
            
            if orchestrator_tasks:
                results = await asyncio.gather(*orchestrator_tasks, return_exceptions=True)
                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        logger.error("orchestrator_execution_error", error=str(res), exc_info=True)
                    else:
                        meta = orchestrator_meta[idx]
                        asyncio.create_task(notification_router.route(
                            tenant_id=int(meta["tenant_id"]),
                            event_type="investigation_completed",
                            payload={"alert_id": meta["alert_id"], "result": str(res)}
                        ))

            logger.info("process_batch_completed", batch_size=batch_size)
            return True
        except Exception as e:
            retries += 1
            if retries > max_retries:
                logger.error("batch_processing_max_retries_reached", batch_size=batch_size, error=str(e), exc_info=True)
                return False
            logger.warning(
                "batch_processing_retrying",
                error=str(e),
                retry=retries,
                max_retries=max_retries,
                backoff=backoff
            )
            await asyncio.sleep(backoff)
            backoff *= 2

    return False

async def dlq_consumer_task() -> None:
    conf = {
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'intelligence_engine_dlq_group',
        'auto.offset.reset': 'earliest'
    }
    while True:
        try:
            consumer = Consumer(conf)
            consumer.subscribe([DLQ_TOPIC])
            logger.info("dlq_consumer_subscribed", topic=DLQ_TOPIC)
            while True:
                await asyncio.sleep(1.0)
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error("dlq_kafka_error", error=str(msg.error()))
                        continue
                
                try:
                    raw_data = msg.value().decode('utf-8')
                    event = json.loads(raw_data)
                    logger.critical("dlq_dead_letter_event_detected", error=event.get('error', 'unknown'))
                except Exception as e:
                    logger.error("dlq_processing_error", error=str(e))
        except Exception as e:
            logger.error("dlq_consumer_loop_failed", error=str(e), exc_info=True)
            await asyncio.sleep(3)
        finally:
            if 'consumer' in locals():
                consumer.close()

async def consume_events() -> None:
    conf = {
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'intelligence_engine_group',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False
    }

    batch_size = 10
    max_batch_size = 100
    min_batch_size = 1
    
    try:
        clickhouse_writer.connect()
    except Exception as e:
        logger.warning("clickhouse_connection_notice", error=str(e))
    
    asyncio.create_task(clickhouse_writer.batch_loop())
    asyncio.create_task(watermark_updater_task())
    
    while True:
        try:
            consumer = Consumer(conf)
            consumer.subscribe([TOPIC])
            logger.info("kafka_consumer_subscribed", topic=TOPIC)

            while True:
                await asyncio.sleep(0.1)
                
                lag_sum = 0
                try:
                    partitions = consumer.assignment()
                    positions = consumer.position(partitions)
                    for p in positions:
                        if p.partition in _watermarks_cache and p.offset > 0:
                            high_watermark = _watermarks_cache[p.partition]
                            lag_sum += max(0, high_watermark - p.offset)
                    KAFKA_LAG_GAUGE.set(lag_sum)
                    logger.debug("consumer_lag_calculated", lag_sum=lag_sum)
                except Exception as e:
                    logger.warning("consumer_lag_check_failed", error=str(e))

                if lag_sum > 1000:
                    batch_size = min(max_batch_size, batch_size * 2)
                elif lag_sum < 100:
                    batch_size = max(min_batch_size, batch_size // 2)

                messages = consumer.consume(num_messages=batch_size, timeout=1.0)
                if not messages:
                    continue
                
                partition_batches = {}
                for msg in messages:
                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue
                        else:
                            logger.error("kafka_message_error", error=str(msg.error()))
                            continue

                    raw_data = None
                    try:
                        raw_data = msg.value().decode('utf-8')
                        event = json.loads(raw_data)
                        
                        p_id = msg.partition()
                        partition_batches.setdefault(p_id, []).append(event)

                    except Exception as e:
                        logger.error("kafka_message_parse_error", error=str(e))
                        if raw_data is not None:
                            route_to_dlq(raw_data, f"JSON parse or unhandled error: {str(e)}")
                
                all_events = [ev for batch in partition_batches.values() for ev in batch]
                if not all_events:
                    consumer.commit(asynchronous=True)
                    continue
                    
                await clickhouse_writer.write_batch(all_events)
                
                worker_tasks = []
                for p_id, batch in partition_batches.items():
                    worker_tasks.append(asyncio.create_task(process_batch_with_retry(batch)))
                    
                results = await asyncio.gather(*worker_tasks, return_exceptions=True)
                for p_idx, res in enumerate(results):
                    if isinstance(res, Exception) or not res:
                        failed_batch = list(partition_batches.values())[p_idx]
                        for ev in failed_batch:
                            route_to_dlq(ev, f"Batch processing failed: {str(res)}")
                            
                consumer.commit(asynchronous=True)
                logger.info("offsets_committed", event_count=len(all_events))

        except Exception as e:
            logger.error("kafka_consumer_loop_failed", error=str(e), exc_info=True)
            await asyncio.sleep(3)
        finally:
            if 'consumer' in locals():
                consumer.close()
