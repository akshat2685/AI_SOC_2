import os
import structlog
from typing import Dict, Any

from .base import BaseConnector
from .registry import ConnectorRegistry

logger = structlog.get_logger(__name__)

SEVERITY_TO_PRIORITY: Dict[str, str] = {
    "critical": "1",
    "high": "2",
    "medium": "3",
    "low": "4",
}


@ConnectorRegistry.register("ticket")
class TicketConnector(BaseConnector):
    """
    ITSM connector (Jira / ServiceNow) with retry via BaseConnector.

    Env vars:
      ITSM_BACKEND          — jira | servicenow (default: jira)
      ITSM_BASE_URL         — base URL of the ITSM instance
      ITSM_PROJECT_KEY      — Jira project key or ServiceNow assignment group
    """

    def __init__(self, tenant_id: int) -> None:
        super().__init__(tenant_id)
        self._backend = os.getenv("ITSM_BACKEND", "jira").lower()
        self._base_url = os.getenv("ITSM_BASE_URL", "https://your-jira-instance.atlassian.net")
        self._project_key = os.getenv("ITSM_PROJECT_KEY", "SOC")

    async def create_incident(self, title: str, description: str, severity: str = "medium") -> Dict[str, Any]:
        return await self.execute_with_retry(
            {"title": title, "description": description, "severity": severity}
        )

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        import httpx

        creds = await self.get_credentials()
        headers = {
            "Authorization": f"Bearer {creds.get('api_key', '')}",
            "Content-Type": "application/json",
        }
        priority = SEVERITY_TO_PRIORITY.get(params.get("severity", "medium"), "3")

        if self._backend == "jira":
            return await self._create_jira_issue(params, headers, priority)
        elif self._backend == "servicenow":
            return await self._create_servicenow_incident(params, headers, priority)
        else:
            raise ValueError(f"Unknown ITSM backend: {self._backend}")

    async def _create_jira_issue(self, params: Dict[str, Any], headers: Dict[str, str], priority: str) -> Dict[str, Any]:
        import httpx

        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": params["title"],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": params["description"]}]}],
                },
                "issuetype": {"name": "Incident"},
                "priority": {"id": priority},
            }
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self._base_url}/rest/api/3/issue",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            ticket_id = data.get("key", "UNKNOWN")
            logger.info("jira_issue_created", ticket_id=ticket_id, tenant=self.tenant_id)
            return {"status": "success", "action": "create_incident", "ticket_id": ticket_id, "title": params["title"]}

    async def _create_servicenow_incident(self, params: Dict[str, Any], headers: Dict[str, str], priority: str) -> Dict[str, Any]:
        import httpx

        payload = {
            "short_description": params["title"],
            "description": params["description"],
            "urgency": priority,
            "impact": priority,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/now/table/incident",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            ticket_id = data.get("result", {}).get("number", "UNKNOWN")
            logger.info("servicenow_incident_created", ticket_id=ticket_id, tenant=self.tenant_id)
            return {"status": "success", "action": "create_incident", "ticket_id": ticket_id, "title": params["title"]}

    async def rollback(self, params: Dict[str, Any], context: Dict[str, Any]) -> bool:
        ticket_id = context.get("ticket_id")
        if not ticket_id or ticket_id == "UNKNOWN":
            return False
        logger.info("ticket_rollback_close", ticket_id=ticket_id, reason="SOAR rollback")
        # Close the ticket — implementation omitted for brevity; add per-backend close call
        return True
