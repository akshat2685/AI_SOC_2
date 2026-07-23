import os
import datetime
import asyncio
from typing import Dict, Any, Optional
import httpx
import structlog

logger = structlog.get_logger(__name__)

def get_required_env(key: str, default: Optional[str] = None) -> str:
    value = os.getenv(key, default)
    if not value:
        raise RuntimeError(f"Required environment variable {key} is not set")
    return value


class SOARAutomationEngine:
    def __init__(
        self,
        db_url: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        self.db_url = db_url or get_required_env("DATABASE_URL") or get_required_env("POSTGRES_URL")
        self.api_key = api_key or get_required_env("SOAR_API_KEY")
        self.endpoint = endpoint or get_required_env("SOAR_API_ENDPOINT")
        self.pool = None

    async def connect(self) -> None:
        """Initialize asyncpg database pool for async database operations."""
        try:
            import asyncpg
            # Normalize postgresql:// scheme for asyncpg if needed
            dsn = self.db_url.replace("postgresql+asyncpg://", "postgresql://")
            self.pool = await asyncpg.create_pool(dsn)
            logger.info("soar_engine_db_connected")
        except Exception as e:
            logger.warning("soar_engine_db_connect_failed", error=str(e))

    async def _log_to_db(
        self,
        risk_score: int,
        action: str,
        status: str,
        response: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Asynchronously log response action to database without blocking event loop."""
        try:
            if self.pool:
                async with self.pool.acquire() as conn:
                    query = """
                    INSERT INTO response_actions (timestamp, risk_score, action, status, api_response)
                    VALUES ($1, $2, $3, $4, $5)
                    """
                    await conn.execute(
                        query,
                        datetime.datetime.now(datetime.timezone.utc),
                        risk_score,
                        action,
                        status,
                        str(response) if response else None,
                    )
            else:
                # Fallback to sync DB execution in thread pool if pool not initialized
                def _sync_db_insert():
                    import psycopg2
                    dsn = self.db_url.replace("postgresql+asyncpg://", "postgresql://")
                    conn = psycopg2.connect(dsn)
                    cursor = conn.cursor()
                    query = """
                    INSERT INTO response_actions (timestamp, risk_score, action, status, api_response)
                    VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.execute(query, (
                        datetime.datetime.now(datetime.timezone.utc),
                        risk_score,
                        action,
                        status,
                        str(response) if response else None
                    ))
                    conn.commit()
                    cursor.close()
                    conn.close()

                await asyncio.to_thread(_sync_db_insert)
            logger.info("soar_action_logged_to_db", action=action, status=status)
        except Exception as e:
            logger.error("soar_db_logging_failed", action=action, error=str(e), exc_info=True)

    async def evaluate_risk_policy(
        self,
        risk_score: int,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Risk-Based Autonomous Response
        0-30: Automatic execution (Low Risk)
        31-70: Approval required (Medium Risk)
        71-100: Human escalation (High Risk)
        """
        logger.info("soar_evaluate_risk_policy", risk_score=risk_score, action=action)
        if risk_score <= 30:
            return await self._execute_automatic(risk_score, action, payload)
        elif risk_score <= 70:
            return await self._request_approval(risk_score, action)
        else:
            return await self._escalate_to_human(risk_score, action)

    async def _execute_automatic(
        self,
        risk_score: int,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        logger.info("soar_auto_executing_low_risk", action=action)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        api_response = None
        status = "executed"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.endpoint}/{action}",
                    headers=headers,
                    json=payload or {"reason": "auto-containment"},
                )
                res.raise_for_status()
                api_response = res.json()
        except Exception as e:
            status = "failed"
            api_response = {"error": str(e)}
            logger.error("soar_api_execution_failed", action=action, error=str(e), exc_info=True)

        await self._log_to_db(risk_score, action, status, api_response)
        return {"status": status, "action": action, "response": api_response}

    async def _request_approval(
        self,
        risk_score: int,
        action: str,
    ) -> Dict[str, Any]:
        logger.info("soar_requesting_approval_medium_risk", action=action)
        status = "pending_approval"
        await self._log_to_db(risk_score, action, status)
        return {"status": status, "action": action}

    async def _escalate_to_human(
        self,
        risk_score: int,
        action: str,
    ) -> Dict[str, Any]:
        logger.warning("soar_escalation_required_high_risk", action=action)
        status = "escalated"
        await self._log_to_db(risk_score, action, status)
        return {"status": status, "action": action}
