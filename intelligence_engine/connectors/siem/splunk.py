from datetime import datetime, timezone
import uuid
from connectors.base import BaseConnector, SecurityEvent

class SplunkConnector(BaseConnector):
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
            "latency_ms": 42,
            "last_sync": datetime.now(timezone.utc).isoformat()
        }

    async def fetch_events(self, since: datetime) -> list[dict]:
        return [
            {
                "id": str(uuid.uuid4()),
                "source_type": "splunk_alert",
                "risk_score": 80,
                "raw": "Mock Splunk alert",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]

    async def normalize(self, event: dict) -> SecurityEvent:
        return SecurityEvent(
            event_id=event.get("id", str(uuid.uuid4())),
            tenant_id=self.tenant_id,
            source="splunk",
            event_type=event.get("source_type", "unknown"),
            severity="HIGH" if event.get("risk_score", 0) > 75 else "MEDIUM",
            timestamp=datetime.fromisoformat(event.get("timestamp", datetime.now(timezone.utc).isoformat())),
            raw_payload=event,
            normalized_payload={"risk": event.get("risk_score")},
            iocs=[],
            mitre_techniques=[],
            topic="siem"
        )

    async def acknowledge(self, event_ids: list[str]) -> None:
        pass

    async def disconnect(self) -> None:
        self._connected = False
        self._authenticated = False
