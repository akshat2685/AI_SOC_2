import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import Response, HTTPStatusError, RequestError

class SimpleCircuitBreaker:
    """Mock Circuit Breaker implementation for testing resilience patterns."""
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 0.5):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN

    async def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            raise RuntimeError("Circuit breaker is OPEN — call blocked")

        try:
            result = await func(*args, **kwargs)
            if self.state == "HALF-OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
            raise e

@pytest.mark.asyncio
async def test_connector_http_500_failure_injection():
    """Test connector retries on HTTP 500 server error."""
    mock_client = AsyncMock()
    # First 2 calls fail with 500, 3rd call succeeds 200
    mock_client.post.side_effect = [
        Response(500, json={"error": "Internal Server Error"}),
        Response(500, json={"error": "Internal Server Error"}),
        Response(200, json={"status": "contained", "action_id": "act-999"})
    ]

    async def execute_soar_containment(client, alert_id: str):
        for attempt in range(3):
            resp = await client.post("https://soar.internal/v1/contain", json={"alert_id": alert_id})
            if resp.status_code == 200:
                return resp.json()
            await asyncio.sleep(0.01)
        raise RuntimeError("SOAR connector failed after max retries")

    res = await execute_soar_containment(mock_client, "alt-100")
    assert res["status"] == "contained"
    assert res["action_id"] == "act-999"
    assert mock_client.post.call_count == 3

@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_repeated_connector_failures():
    """Test circuit breaker state transition from CLOSED to OPEN after reaching threshold."""
    cb = SimpleCircuitBreaker(failure_threshold=3, recovery_timeout=0.1)

    async def failing_connector_call():
        raise RequestError("Network unreachable")

    # 3 failures -> threshold reached -> state becomes OPEN
    for _ in range(3):
        with pytest.raises(RequestError):
            await cb.call(failing_connector_call)

    assert cb.state == "OPEN"

    # Subsequent call while OPEN should fail fast with RuntimeError
    with pytest.raises(RuntimeError, match="Circuit breaker is OPEN"):
        await cb.call(failing_connector_call)

@pytest.mark.asyncio
async def test_connector_fallback_degradation():
    """Test that when external connector fails, fallback stub is invoked gracefully."""
    connector_active = False

    async def dispatch_security_action(action_name: str, payload: dict):
        if not connector_active:
            # Fallback to local stub response
            return {
                "action": action_name,
                "status": "stub_fallback_executed",
                "execution_mode": "offline_stub",
                "details": payload
            }
        return {"action": action_name, "status": "executed_live"}

    result = await dispatch_security_action("isolate_host", {"hostname": "workstation-12"})
    assert result["status"] == "stub_fallback_executed"
    assert result["execution_mode"] == "offline_stub"
    assert result["details"]["hostname"] == "workstation-12"
