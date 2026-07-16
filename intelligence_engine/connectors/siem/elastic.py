"""Elastic SIEM Connector."""

from datetime import datetime, timezone
from typing import Any

from intelligence_engine.connectors.base import BaseConnector, SecurityEvent

class ElasticConnector(BaseConnector):
    """Connector for Elastic SIEM."""

    def __init__(self, tenant_id: str, endpoint: str, api_key: str):
        self.tenant_id = tenant_id
        self.endpoint = endpoint
        self.api_key = api_key
        self.connected = False
        self.authenticated = False

    async def connect(self) -> None:
        """Establish the underlying transport."""
        self.connected = True

    async def authenticate(self) -> None:
        """Authenticate against the remote API."""
        import httpx
        from fastapi import HTTPException
        
        headers = {
            "Authorization": f"ApiKey {self.api_key}",
            "Content-Type": "application/json"
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.endpoint}/_security/_authenticate",
                    headers=headers,
                    timeout=5.0
                )
                if response.status_code == 200:
                    self.authenticated = True
                else:
                    self.authenticated = False
                    raise HTTPException(status_code=401, detail="Invalid Elastic API Key")
        except Exception as e:
            self.authenticated = False
            raise ValueError(f"Elastic authentication failed: {e}")

    async def health(self) -> dict:
        """Return connector health."""
        return {
            "status": "healthy" if self.connected and self.authenticated else "unhealthy",
            "latency_ms": 15,
            "last_sync": datetime.now(timezone.utc).isoformat()
        }

    async def fetch_events(self, since: datetime) -> list[dict]:
        """Fetch raw events created after *since* from the source."""
        # Stub implementation
        return []

    async def normalize(self, event: dict) -> SecurityEvent:
        """Convert a single raw event dict into a SecurityEvent."""
        return SecurityEvent(
            event_id=str(event.get("_id", "unknown_elastic_id")),
            tenant_id=self.tenant_id,
            source="elastic_siem",
            event_type=str(event.get("event", {}).get("action", "elastic_event")),
            severity=str(event.get("event", {}).get("severity", "LOW")).upper(),
            timestamp=datetime.now(timezone.utc),
            raw_payload=event,
            normalized_payload=event.get("event", {}),
            iocs=[],
            mitre_techniques=[],
            topic="siem"
        )

    async def acknowledge(self, event_ids: list[str]) -> None:
        """Mark the given event IDs as processed / acknowledged upstream."""
        pass

    async def disconnect(self) -> None:
        """Tear down the connection and release resources."""
        self.connected = False
        self.authenticated = False
