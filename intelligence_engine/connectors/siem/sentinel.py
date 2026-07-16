import aiohttp
from datetime import datetime, timezone
from typing import Any

from ..base import BaseConnector, SecurityEvent, Severity


class SentinelConnector(BaseConnector):
    """Microsoft Sentinel connector supporting Azure OAuth2 Client Credentials Flow."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, workspace_id: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.workspace_id = workspace_id
        
        self.access_token = None
        self.session = None
        self.base_url = f"https://api.loganalytics.io/v1/workspaces/{self.workspace_id}"
        self.auth_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

    async def connect(self) -> None:
        """Establish the underlying transport."""
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def authenticate(self) -> None:
        """Authenticate using Azure OAuth2 Client Credentials flow."""
        if not self.session:
            await self.connect()

        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "resource": "https://api.loganalytics.io"
        }
        async with self.session.post(self.auth_url, data=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self.access_token = data.get("access_token")

    async def health(self) -> dict:
        """Return connector health."""
        if not self.access_token:
            return {"status": "unhealthy", "latency_ms": 0, "last_sync": None}
            
        start = datetime.now()
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            query = {"query": "SecurityEvent | take 1"}
            async with self.session.post(f"{self.base_url}/query", headers=headers, json=query) as resp:
                resp.raise_for_status()
                latency = (datetime.now() - start).total_seconds() * 1000
                return {
                    "status": "healthy",
                    "latency_ms": latency,
                    "last_sync": datetime.now(timezone.utc).isoformat()
                }
        except Exception:
            return {"status": "degraded", "latency_ms": 0, "last_sync": None}

    async def fetch_events(self, since: datetime) -> list[dict]:
        """Fetch raw events from Sentinel (Log Analytics Workspace) since the given time."""
        if not self.access_token:
            await self.authenticate()
            
        headers = {"Authorization": f"Bearer {self.access_token}"}
        time_format = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        query = {
            "query": f"SecurityIncident | where TimeGenerated > datetime('{time_format}') | order by TimeGenerated asc"
        }
        
        async with self.session.post(f"{self.base_url}/query", headers=headers, json=query) as resp:
            resp.raise_for_status()
            data = await resp.json()
            
            tables = data.get("tables", [])
            if not tables:
                return []
                
            columns = [col["name"] for col in tables[0].get("columns", [])]
            rows = tables[0].get("rows", [])
            
            events = []
            for row in rows:
                event = dict(zip(columns, row))
                events.append(event)
                
            return events

    async def normalize(self, event: dict) -> SecurityEvent:
        """Convert a Sentinel raw event into a SecurityEvent."""
        severity_mapping = {
            "low": Severity.LOW,
            "medium": Severity.MEDIUM,
            "high": Severity.HIGH,
            "critical": Severity.CRITICAL
        }
        
        raw_sev = str(event.get("Severity", "low")).lower()
        severity = severity_mapping.get(raw_sev, Severity.LOW)
        
        event_id = event.get("IncidentNumber", event.get("TenantId", "unknown-id"))
        
        time_generated = event.get("TimeGenerated")
        if time_generated:
            try:
                timestamp = datetime.fromisoformat(time_generated.replace('Z', '+00:00'))
            except ValueError:
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)
            
        return SecurityEvent(
            event_id=str(event_id),
            tenant_id=event.get("TenantId", self.workspace_id),
            source="sentinel",
            event_type=event.get("Title", "Unknown Incident"),
            severity=severity,
            timestamp=timestamp,
            raw_payload=event,
            normalized_payload={"status": event.get("Status")},
            iocs=[],
            mitre_techniques=[],
            topic="siem.sentinel"
        )

    async def acknowledge(self, event_ids: list[str]) -> None:
        """Mark events as processed."""
        # Typically handled via Graph API for Sentinel
        pass

    async def disconnect(self) -> None:
        """Tear down the connection and release resources."""
        if self.session:
            await self.session.close()
            self.session = None
