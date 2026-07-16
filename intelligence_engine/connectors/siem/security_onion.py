from datetime import datetime, timezone
import uuid
from connectors.base import BaseConnector, SecurityEvent

class SecurityOnionConnector(BaseConnector):
    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        self._connected = False
        self._authenticated = False

    async def connect(self) -> None:
        self._connected = True

    async def authenticate(self) -> None:
        self._authenticated = True

    async def health(self) -> dict:
        return {
            "status": "healthy" if self._connected and self._authenticated else "unhealthy",
            "latency_ms": 30,
            "last_sync": datetime.now(timezone.utc).isoformat()
        }

    async def fetch_events(self, since: datetime) -> list[dict]:
        return [
            {
                "alert_id": str(uuid.uuid4()),
                "rule_name": "suricata_alert",
                "severity_label": "High",
                "details": "Mock Security Onion alert",
                "ts": datetime.now(timezone.utc).isoformat()
            }
        ]

    async def normalize(self, event: dict) -> SecurityEvent:
        severity_map = {
            "low": "LOW",
            "medium": "MEDIUM",
            "high": "HIGH",
            "critical": "CRITICAL"
        }
        raw_sev = event.get("severity_label", "medium").lower()
        severity = severity_map.get(raw_sev, "MEDIUM")

        return SecurityEvent(
            event_id=event.get("alert_id", str(uuid.uuid4())),
            tenant_id=self.tenant_id,
            source="security_onion",
            event_type=event.get("rule_name", "unknown"),
            severity=severity,
            timestamp=datetime.fromisoformat(event.get("ts", datetime.now(timezone.utc).isoformat())),
            raw_payload=event,
            normalized_payload={"details": event.get("details")},
            iocs=[],
            mitre_techniques=[],
            topic="siem"
        )

    async def acknowledge(self, event_ids: list[str]) -> None:
        pass

    async def disconnect(self) -> None:
        self._connected = False
        self._authenticated = False
