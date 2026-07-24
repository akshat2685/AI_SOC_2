import os
import asyncio
import structlog
from typing import Dict, Any

from .base import BaseConnector
from .registry import ConnectorRegistry

logger = structlog.get_logger(__name__)


@ConnectorRegistry.register("firewall")
class FirewallConnector(BaseConnector):
    """
    Firewall connector with exponential-backoff retry via BaseConnector.

    Env vars:
      FIREWALL_API_URL      — base URL of firewall management API
      FIREWALL_API_KEY_PATH — Vault path to retrieve the API key (optional)
    """

    def __init__(self, tenant_id: int) -> None:
        super().__init__(tenant_id)
        self._api_url = os.getenv("FIREWALL_API_URL", "http://firewall-api:8080")

    # ------------------------------------------------------------------
    # Public helpers — use execute_with_retry for transient-failure safety
    # ------------------------------------------------------------------

    async def block_ip(self, ip_address: str) -> Dict[str, Any]:
        return await self.execute_with_retry({"action": "block_ip", "ip": ip_address})

    async def unblock_ip(self, ip_address: str) -> Dict[str, Any]:
        return await self.execute_with_retry({"action": "unblock_ip", "ip": ip_address})

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        import httpx

        action = params["action"]
        ip = params["ip"]
        creds = await self.get_credentials()

        headers = {"Authorization": f"Bearer {creds.get('api_key', '')}"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            if action == "block_ip":
                resp = await client.post(
                    f"{self._api_url}/v1/block",
                    json={"ip": ip, "tenant_id": self.tenant_id},
                    headers=headers,
                )
            elif action == "unblock_ip":
                resp = await client.delete(
                    f"{self._api_url}/v1/block/{ip}",
                    params={"tenant_id": self.tenant_id},
                    headers=headers,
                )
            else:
                raise ValueError(f"Unknown firewall action: {action}")

            resp.raise_for_status()
            result = resp.json()
            logger.info("firewall_action_success", action=action, ip=ip, tenant=self.tenant_id)
            return result

    async def rollback(self, params: Dict[str, Any], context: Dict[str, Any]) -> bool:
        # Rollback a block by unblocking; rollback an unblock by re-blocking
        reverse = {"block_ip": "unblock_ip", "unblock_ip": "block_ip"}
        reverse_action = reverse.get(params.get("action", ""), "")
        if not reverse_action:
            return False
        try:
            await self.execute({"action": reverse_action, "ip": params["ip"]})
            return True
        except Exception as exc:
            logger.error("firewall_rollback_failed", error=str(exc), params=params)
            return False
