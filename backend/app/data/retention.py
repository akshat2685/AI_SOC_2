"""GDPR-compliant data retention policies and expiry calculations module."""
from datetime import datetime, timedelta
from typing import Dict


RETENTION_RULES: Dict[str, int] = {
    "alerts": 90,
    "incidents": 365,
    "audit_log": 2555,  # 7 years
    "telemetry": 30,
    "sessions": 7,
}


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
        return datetime.utcnow() - timedelta(days=days)


retention_policy = RetentionPolicy()
