"""GDPR-compliant data retention policies and expiry calculations module."""
from datetime import datetime, timedelta, timezone
from typing import Dict

import structlog
from sqlalchemy import delete, select

logger = structlog.get_logger(__name__)


RETENTION_RULES: Dict[str, int] = {
    "alerts": 90,
    "incidents": 365,
    "audit_log": 2555,  # 7 years
    "telemetry": 30,
    "sessions": 7,
}

_PURGE_BATCH_SIZE = 5000


class RetentionPolicy:
    """Calculates data expiration timestamps according to governance retention rules."""

    def __init__(self, rules: Dict[str, int] = RETENTION_RULES):
        self.rules = rules

    def get_retention_days(self, data_type: str) -> int:
        """Get the retention period in days for a specific data type."""
        return self.rules.get(data_type.lower(), 90)

    def get_expiry_date(self, data_type: str) -> datetime:
        """Calculate the UTC timestamp before which data should be purged or archived."""
        days = self.get_retention_days(data_type)
        return datetime.now(timezone.utc) - timedelta(days=days)


retention_policy = RetentionPolicy()


async def purge_expired_data(db) -> Dict[str, int]:
    """Delete rows older than their retention window, in batches.

    Purged (alerts 90d, incidents 365d, telemetry/security_events 30d).
    Deliberately NOT purged:
      - audit_log: the tamper-evident hash chain depends on contiguous
        history, and 7-year compliance retention means archive, not silent
        delete. Deleting rows would also trip the on-read chain verifier.
      - sessions: no sessions table exists; nothing to purge.

    Order matters: alerts before incidents, so FK references from alerts to
    incidents are gone before their incidents are deleted. Runs under the
    service scope (spans tenants) — callers must use service_scope().
    Returns {table: rows_deleted}.
    """
    # Local import: app.data must not import domain models at module load
    # (keeps the pure calculation helpers importable without the ORM).
    from app.domain.models import Alert, Incident, SecurityEvent

    now = datetime.now(timezone.utc)
    targets = [
        ("alerts", Alert, Alert.timestamp, RETENTION_RULES["alerts"]),
        ("incidents", Incident, Incident.created_at, RETENTION_RULES["incidents"]),
        ("telemetry", SecurityEvent, SecurityEvent.observed_at, RETENTION_RULES["telemetry"]),
    ]

    deleted: Dict[str, int] = {}
    for name, model, ts_col, days in targets:
        cutoff = now - timedelta(days=days)
        total = 0
        while True:
            subq = select(model.id).where(ts_col < cutoff).limit(_PURGE_BATCH_SIZE)
            result = await db.execute(delete(model).where(model.id.in_(subq)))
            await db.commit()
            n = result.rowcount or 0
            total += n
            if n < _PURGE_BATCH_SIZE:
                break
        deleted[name] = total
        if total:
            logger.info("retention_purged", table=name, rows=total, older_than_days=days)

    logger.info("retention_purge_skipped_audit_log",
                reason="hash-chain integrity + 7y compliance retention: archive, never delete")
    return deleted
