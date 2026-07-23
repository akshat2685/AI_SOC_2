import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from intelligence_engine.soar.automation_engine import SOARAutomationEngine


@pytest.fixture
def engine():
    return SOARAutomationEngine(
        db_url="postgresql://test:test@localhost/testdb",
        api_key="test_key",
        endpoint="http://test.local/api"
    )


@pytest.mark.asyncio
async def test_evaluate_risk_policy_low(engine):
    with patch.object(engine, '_execute_automatic', new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"status": "executed", "action": "block_ip", "response": {"success": True}}
        result = await engine.evaluate_risk_policy(20, "block_ip")
        assert result["status"] == "executed"
        mock_exec.assert_called_once_with(20, "block_ip", None)


@pytest.mark.asyncio
async def test_evaluate_risk_policy_medium(engine):
    with patch.object(engine, '_request_approval', new_callable=AsyncMock) as mock_approve:
        mock_approve.return_value = {"status": "pending_approval", "action": "isolate_host"}
        result = await engine.evaluate_risk_policy(50, "isolate_host")
        assert result["status"] == "pending_approval"
        mock_approve.assert_called_once_with(50, "isolate_host")


@pytest.mark.asyncio
async def test_evaluate_risk_policy_high(engine):
    with patch.object(engine, '_escalate_to_human', new_callable=AsyncMock) as mock_esc:
        mock_esc.return_value = {"status": "escalated", "action": "shutdown_server"}
        result = await engine.evaluate_risk_policy(80, "shutdown_server")
        assert result["status"] == "escalated"
        mock_esc.assert_called_once_with(80, "shutdown_server")


@pytest.mark.asyncio
async def test_execute_automatic_success(engine):
    with patch("intelligence_engine.soar.automation_engine.httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_client_instance = mock_client.return_value.__aenter__.return_value
        mock_client_instance.post = AsyncMock(return_value=mock_response)

        with patch.object(engine, '_log_to_db', new_callable=AsyncMock) as mock_log:
            result = await engine._execute_automatic(20, "block_ip", {"ip": "1.1.1.1"})
            assert result["status"] == "executed"
            mock_log.assert_called_once()
