import os
import json
import asyncio
import structlog
import uuid
import time
from datetime import datetime, timezone
import psycopg2
from confluent_kafka import Consumer, KafkaError

try:
    from intelligence_engine.core.memory_learning import MemoryLearningSystem
except ImportError:
    from core.memory_learning import MemoryLearningSystem

try:
    from intelligence_engine.core.notification_router import router as notification_router
except ImportError:
    from core.notification_router import router as notification_router

logger = structlog.get_logger("compliance_consumer")

KAFKA_BROKER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
POSTGRES_URL = os.getenv("POSTGRES_URL", "")
TOPICS = ["soc_telemetry", "audit_events"]

class ComplianceEvaluator:
    def __init__(self):
        self.rules_cache = []
        self.last_sync = 0
        self.sync_interval = 60 # seconds
        self.memory_system = MemoryLearningSystem(dsn=POSTGRES_URL.replace('postgresql://', 'postgresql://') if POSTGRES_URL else None)
        self.db_conn = None

    def _get_db(self):
        if not self.db_conn or self.db_conn.closed != 0:
            self.db_conn = psycopg2.connect(POSTGRES_URL)
        return self.db_conn
        
    def sync_rules(self):
        try:
            conn = self._get_db()
            with conn.cursor() as cur:
                # fetch active rules
                cur.execute("SELECT id, control_id, rule_expression FROM compliance_rules WHERE is_active = True")
                rules = cur.fetchall()
                self.rules_cache = [{"id": r[0], "control_id": r[1], "expression": r[2]} for r in rules]
                self.last_sync = time.time()
                logger.info(f"[Compliance] Synced {len(self.rules_cache)} rules.")
        except Exception as e:
            logger.error(f"[Compliance] Failed to sync rules: {e}")

    def evaluate_event(self, event: dict):
        if time.time() - self.last_sync > self.sync_interval:
            self.sync_rules()
            
        violations = []
        for rule in self.rules_cache:
            expr = rule["expression"]
            try:
                if "==" in expr:
                    key_path, expected = expr.split("==")
                    key_path = key_path.strip()
                    expected = expected.strip()
                    
                    current = event
                    found = True
                    for part in key_path.split("."):
                        if isinstance(current, dict) and part in current:
                            current = current[part]
                        else:
                            found = False
                            break
                            
                    if found:
                        current_str = str(current).lower()
                        expected_str = str(expected).lower()
                        if current_str != expected_str:
                            violations.append(rule)
            except Exception as e:
                pass
                
        return violations

    async def handle_violations(self, event: dict, violations: list):
        tenant_id = event.get("tenant_id", 1)
        asset_id = event.get("asset_id", None)
        event_id = event.get("event_id", str(uuid.uuid4()))
        
        for v in violations:
            logger.warning(f"[Compliance] Violation detected! Rule {v['id']} failed for event {event_id}")
            
            # 1. Insert into PostgreSQL
            try:
                def _insert():
                    conn = self._get_db()
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO compliance_violations (tenant_id, rule_id, asset_id, event_id, status, details, detected_at) 
                            VALUES (%s, %s, %s, %s, 'OPEN', %s, %s)
                            """,
                            (tenant_id, v["id"], asset_id, event_id, json.dumps(event), datetime.now(timezone.utc))
                        )
                        conn.commit()
                await asyncio.to_thread(_insert)
            except Exception as e:
                logger.error(f"[Compliance] DB Insert Error: {e}")
                
            # 2. Index to Memory Platform
            try:
                incident_data = {
                    "violation": True,
                    "rule_id": v["id"],
                    "asset_id": asset_id,
                    "event_data": event
                }
                await asyncio.to_thread(self.memory_system.record_incident, event_id, incident_data, "OPEN")
            except Exception as e:
                logger.error(f"[Compliance] Memory Index Error: {e}")
                
            # 3. Stream real-time notification
            try:
                await notification_router.route(
                    tenant_id=int(tenant_id),
                    event_type="compliance_violation",
                    payload={"rule_id": v["id"], "event_id": event_id, "severity": "HIGH", "asset_id": asset_id}
                )
            except Exception as e:
                logger.error(f"[Compliance] Notification Error: {e}")

async def run_compliance_stream():
    evaluator = ComplianceEvaluator()
    evaluator.sync_rules()
    
    conf = {
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'compliance_stream_processor',
        'auto.offset.reset': 'earliest'
    }
    
    consumer = Consumer(conf)
    consumer.subscribe(TOPICS)
    logger.info(f"[Compliance] Subscribed to {TOPICS}")
    
    try:
        while True:
            msg = await asyncio.to_thread(consumer.poll, 1.0)
            if msg is None:
                await asyncio.sleep(0.1)
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    logger.error(f"[Compliance] Kafka error: {msg.error()}")
                continue
                
            try:
                event = json.loads(msg.value().decode('utf-8'))
                violations = evaluator.evaluate_event(event)
                if violations:
                    await evaluator.handle_violations(event, violations)
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"[Compliance] Error processing message: {e}")
                
    except asyncio.CancelledError:
        pass
    finally:
        consumer.close()

if __name__ == "__main__":
    asyncio.run(run_compliance_stream())
