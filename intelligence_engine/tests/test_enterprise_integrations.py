import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from intelligence_engine.core.enterprise_integrations import (
    CircuitBreaker, CircuitBreakerOpenException,
    ServiceNowWorker, JiraWorker, SlackWorker
)
import aiohttp

# Create a mock for EventBus without importing the real one, in case it's not fully implemented or available in this context
class DummyEventBus:
    pass

@pytest.fixture
def event_bus():
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()
    return bus

@pytest.mark.asyncio
async def test_circuit_breaker_success():
    cb = CircuitBreaker(max_failures=2, reset_timeout=1)
    
    async def success_func():
        return "success"
    
    result = await cb.call(success_func)
    assert result == "success"
    assert cb.state == "CLOSED"

@pytest.mark.asyncio
async def test_circuit_breaker_failure_and_open():
    cb = CircuitBreaker(max_failures=2, reset_timeout=1)
    
    async def fail_func():
        raise ValueError("Failed")

    with pytest.raises(ValueError):
        await cb.call(fail_func)
        
    assert cb.failures == 1
    assert cb.state == "CLOSED"

    with pytest.raises(ValueError):
        await cb.call(fail_func)
        
    assert cb.failures == 2
    assert cb.state == "OPEN"

    with pytest.raises(CircuitBreakerOpenException):
        await cb.call(fail_func)

@pytest.mark.asyncio
@patch('intelligence_engine.core.enterprise_integrations.secrets_manager')
@patch('asyncio.create_subprocess_exec')
async def test_servicenow_incident_create_success(mock_create_subprocess_exec, mock_secrets, event_bus):
    mock_secrets.get_secret.return_value = "test_conn"
    
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b'success output', b'')
    mock_process.returncode = 0
    mock_create_subprocess_exec.return_value = mock_process
    
    worker = ServiceNowWorker(event_bus)
    await worker.start()
    
    event_bus.subscribe.assert_any_call("incident.create", worker.handle_incident_create)
    
    await worker.handle_incident_create({"title": "Test Incident", "description": "Desc"})
    
    event_bus.publish.assert_called_with("incident.created.success", {"result": "success output"})

@pytest.mark.asyncio
@patch('intelligence_engine.core.enterprise_integrations.secrets_manager')
@patch('aiohttp.ClientSession.request')
async def test_jira_ticket_transition(mock_request, mock_secrets, event_bus):
    mock_secrets.get_secret.side_effect = lambda d, k: "test_val"
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {"status": "ok"}
    
    mock_request_ctx = AsyncMock()
    mock_request_ctx.__aenter__.return_value = mock_response
    mock_request.return_value = mock_request_ctx

    worker = JiraWorker(event_bus)
    await worker.handle_ticket_transition({"ticket_id": "PROJ-123", "transition_id": "31"})
    
    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert "/rest/api/3/issue/PROJ-123/transitions" in args[1]
    assert kwargs["json"] == {"transition": {"id": "31"}}

@pytest.mark.asyncio
@patch('intelligence_engine.core.enterprise_integrations.secrets_manager')
@patch('aiohttp.ClientSession.post')
async def test_slack_alert(mock_post, mock_secrets, event_bus):
    mock_secrets.get_secret.return_value = "https://hooks.slack.com/test"
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text.return_value = "ok"
    
    mock_request_ctx = AsyncMock()
    mock_request_ctx.__aenter__.return_value = mock_response
    mock_post.return_value = mock_request_ctx

    worker = SlackWorker(event_bus)
    await worker.handle_alert({"title": "High CPU", "description": "Server is at 99%", "severity": "HIGH"})
    
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    blocks = kwargs["json"]["blocks"]
    assert len(blocks) == 1
    assert "HIGH ALERT" in blocks[0]["text"]["text"]
