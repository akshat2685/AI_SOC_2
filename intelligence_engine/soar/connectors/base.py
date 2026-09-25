import asyncio
import os
import structlog
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = structlog.get_logger(__name__)

class BaseConnector(ABC):
    """
    Abstract Base Class for all SOAR Connectors.
    Provides standardized execute and rollback methods with exponential backoff.
    """
    def __init__(self, tenant_id: int):
        self.tenant_id = tenant_id
        
    async def get_credentials(self) -> Dict[str, str]:
        """
        Retrieves credentials for the target system.

        Reads SOAR_CONNECTOR_API_KEY from the environment. (The original
        TenantKeyStore integration is not wired in this build, so env is
        the explicit source -- there is intentionally no mock fallback.)
        """
        api_key = os.environ.get("SOAR_CONNECTOR_API_KEY", "")
        if not api_key:
            logger.warning(
                "soar_connector_no_api_key",
                hint="Set SOAR_CONNECTOR_API_KEY for live connector actions.",
            )
        return {"api_key": api_key}

    async def execute_with_retry(self, action_params: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """
        Executes the connector action with built-in exponential backoff and jitter.
        """
        import random
        for attempt in range(max_retries):
            try:
                return await self.execute(action_params)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Connector execution failed after {max_retries} attempts: {e}")
                    raise
                
                # Exponential backoff with jitter
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Connector error: {e}. Retrying in {sleep_time:.2f}s...")
                await asyncio.sleep(sleep_time)

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Specific implementation for executing an action."""
        pass

    @abstractmethod
    async def rollback(self, params: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Specific implementation for rolling back an action."""
        pass
