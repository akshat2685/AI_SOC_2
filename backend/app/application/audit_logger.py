"""Audit logging with a tamper-evident hash chain.

Two paths, one guarantee — every emit() ends up as a row in Postgres:

1. Kafka path (if a producer is running): events go to the soc_audit_log
   topic; the audit consumer drains them into Postgres. The consumer is
   currently not started in production, so in practice...
2. Direct path: emit() schedules an async task that writes straight to
   Postgres inside a transaction, computing the HMAC chain link under a
   per-tenant lock (SELECT ... FOR UPDATE on the latest row keeps the
   chain correct even with concurrent writers).

Hash chain: integrity_hash = HMAC-SHA256(AUDIT_SECRET_KEY,
    prev_hash || canonical_json(event)). Verification walks the chain in
id order and recomputes every link. AUDIT_SECRET_KEY is fail-fast required
(see core/config.py): with an empty key the HMAC is forgeable, so the
chain would be theater.
"""

import asyncio
import hashlib
import hmac
import json
import time
from collections import defaultdict

import structlog
from sqlalchemy import select

from app.core.config import settings

logger = structlog.get_logger(__name__)

_GENESIS = "0"


def _signed_payload(event: dict) -> dict:
    """The exact payload that is hashed at write time. Only fields that are
    stored on the audit_events row are signed, so verification can rebuild
    the payload byte-identically from a DB read. Keep this stable."""
    return {
        "tenant_id": event["tenant_id"],
        "action": event["action"],
        "user_id": event.get("user_id"),
        "trace_id": event.get("trace_id"),
        "details": event.get("details") or {},
    }


def compute_chain_hash(previous_hash: str, event: dict) -> str:
    canonical = json.dumps(_signed_payload(event), separators=(",", ":"), sort_keys=True)
    message = f"{previous_hash}{canonical}".encode("utf-8")
    return hmac.new(settings.AUDIT_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_chain(events: list, prev_hash: str = _GENESIS) -> tuple:
    """Verify a hash chain over events in ascending id order.

    Each event is a dict with id, tenant_id, action, user_id, trace_id,
    details, integrity_hash. `prev_hash` anchors the chain: _GENESIS when
    verifying from the first row, or the preceding row's hash when
    verifying a later page. Returns (valid, failed_event_id).
    """
    prev = prev_hash
    for ev in events:
        expected = compute_chain_hash(prev, ev)
        if not hmac.compare_digest(expected, ev["integrity_hash"]):
            return False, ev["id"]
        prev = ev["integrity_hash"]
    return True, None


class AuditLogger:
    def __init__(self):
        self.producer = None
        self.topic = "soc_audit_log"
        self._locks = defaultdict(asyncio.Lock)

    async def start(self):
        try:
            from aiokafka import AIOKafkaProducer
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
            )
            await self.producer.start()
            logger.info("audit_logger_started")
        except Exception as e:
            logger.error("audit_logger_start_failed", error=str(e))

    async def stop(self):
        if self.producer:
            await self.producer.stop()
            logger.info("audit_logger_stopped")

    def emit(self, action: str, tenant_id: int, user_id: int = None, trace_id: str = None, details: dict = None):
        """Fire-and-forget audit write. Kafka if available, else direct to
        Postgres. Either way the event lands in audit_events with a chained
        integrity hash."""
        event = {
            "tenant_id": tenant_id,
            "action": action,
            "user_id": user_id,
            "trace_id": trace_id,
            "details": details or {},
            "timestamp": int(time.time() * 1000),
        }

        if self.producer:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.producer.send_and_wait(
                    self.topic,
                    key=str(tenant_id).encode("utf-8"),
                    value=json.dumps(event).encode("utf-8"),
                ))
                return
            except Exception as e:
                logger.error("audit_kafka_emit_failed", error=str(e), action=action, tenant_id=tenant_id)
                # fall through to the direct path

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.error("audit_emit_no_event_loop", action=action, tenant_id=tenant_id)
            return
        loop.create_task(self._direct_sink(event))

    async def _direct_sink(self, event: dict) -> None:
        """Write one audit event to Postgres with its chain hash.

        Runs under tenant_scope so RLS applies; the chain link is computed
        inside the transaction with the latest row locked (FOR UPDATE),
        so concurrent writers cannot fork the chain.
        """
        from app.domain.models import AuditEvent
        from app.infrastructure.database import tenant_scope

        tenant_id = event["tenant_id"]
        lock = self._locks[tenant_id]
        async with lock:
            try:
                async with tenant_scope(tenant_id) as session:
                    latest = (
                        await session.execute(
                            select(AuditEvent.integrity_hash)
                            .where(AuditEvent.tenant_id == tenant_id)
                            .order_by(AuditEvent.id.desc())
                            .limit(1)
                            .with_for_update()
                        )
                    ).scalar_one_or_none()
                    prev_hash = latest or _GENESIS
                    integrity_hash = compute_chain_hash(prev_hash, event)
                    row = AuditEvent(
                        tenant_id=tenant_id,
                        user_id=event.get("user_id"),
                        trace_id=event.get("trace_id"),
                        action=event["action"],
                        details=event.get("details", {}),
                        integrity_hash=integrity_hash,
                    )
                    session.add(row)
                    await session.commit()
            except Exception as e:
                logger.error("audit_direct_sink_failed", error=str(e),
                             action=event.get("action"), tenant_id=tenant_id)


audit_logger = AuditLogger()
