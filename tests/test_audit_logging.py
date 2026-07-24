import pytest
import json
import hashlib
import hmac
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import Request
from sqlalchemy import text
from app.domain.models import AuditEvent
from app.application.audit_logger import AuditLogger
from app.infrastructure.audit_consumer import AuditConsumer
from app.api.middleware.audit_middleware import AuditMiddleware
from app.core.config import settings

@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr(settings, "AUDIT_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

def test_audit_event_model():
    """Test AuditEvent model fields."""
    event = AuditEvent(
        tenant_id=1,
        user_id=42,
        trace_id="test-trace-id",
        action="test_action",
        details={"key": "value"},
        integrity_hash="test-hash"
    )
    assert event.tenant_id == 1
    assert event.user_id == 42
    assert event.trace_id == "test-trace-id"
    assert event.action == "test_action"
    assert event.details == {"key": "value"}
    assert event.integrity_hash == "test-hash"

@pytest.mark.asyncio
async def test_audit_middleware_captures_mutating_requests(monkeypatch):
    """Test that AuditMiddleware captures POST/PUT/PATCH/DELETE requests."""
    from app.core.auth import current_tenant_id, current_user_id, current_trace_id
    
    current_tenant_id.set(1)
    current_user_id.set(42)
    current_trace_id.set("test-trace")
    
    mock_emit = MagicMock()
    monkeypatch.setattr("app.api.middleware.audit_middleware.audit_logger.emit", mock_emit)
    
    app = MagicMock()
    middleware = AuditMiddleware(app)
    
    # Mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/test",
        "client": ("127.0.0.1", 8000),
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
    }
    request = Request(scope)
    
    mock_response = AsyncMock()
    mock_response.status_code = 200
    
    async def call_next(req):
        return mock_response
        
    response = await middleware.dispatch(request, call_next)
    
    assert response == mock_response
    mock_emit.assert_called_once()
    kwargs = mock_emit.call_args.kwargs
    assert kwargs["action"] == "http_post"
    assert kwargs["tenant_id"] == 1
    assert kwargs["user_id"] == 42
    assert kwargs["trace_id"] == "test-trace"
    assert kwargs["details"]["path"] == "/api/test"
    assert kwargs["details"]["status_code"] == 200

@pytest.mark.asyncio
async def test_audit_middleware_ignores_get_requests(monkeypatch):
    """Test that AuditMiddleware ignores GET requests."""
    mock_emit = MagicMock()
    monkeypatch.setattr("app.api.middleware.audit_middleware.audit_logger.emit", mock_emit)
    
    app = MagicMock()
    middleware = AuditMiddleware(app)
    
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
    }
    request = Request(scope)
    mock_response = AsyncMock()
    
    async def call_next(req):
        return mock_response
        
    await middleware.dispatch(request, call_next)
    mock_emit.assert_not_called()

@pytest.mark.asyncio
async def test_audit_consumer_compute_hash(mock_settings, monkeypatch):
    """Test the integrity chain HMAC logic."""
    mock_session = AsyncMock()
    mock_session_local = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "db-hash"
    mock_session.execute.return_value = mock_result
    
    monkeypatch.setattr("app.infrastructure.audit_consumer.AsyncSessionLocal", mock_session_local)

    consumer = AuditConsumer()
    tenant_id = 1
    event_data = {"action": "test_action", "details": {}}
    
    # First hash (cache miss, loads "db-hash" from DB)
    hash1 = await consumer._compute_hash(tenant_id, event_data)
    
    # Expected logic for hash1
    canonical_event = json.dumps(event_data, separators=(',', ':'), sort_keys=True)
    message = f"db-hash{canonical_event}".encode('utf-8')
    expected_hash1 = hmac.new(b"test-secret-key", message, hashlib.sha256).hexdigest()
    assert hash1 == expected_hash1
    assert consumer.tenant_hashes[tenant_id] == hash1
    
    # Second hash (chaining, cache hit)
    event_data_2 = {"action": "test_action_2", "details": {}}
    hash2 = await consumer._compute_hash(tenant_id, event_data_2)
    
    canonical_event_2 = json.dumps(event_data_2, separators=(',', ':'), sort_keys=True)
    message_2 = f"{hash1}{canonical_event_2}".encode('utf-8')
    expected_hash2 = hmac.new(b"test-secret-key", message_2, hashlib.sha256).hexdigest()
    assert hash2 == expected_hash2
    assert consumer.tenant_hashes[tenant_id] == hash2

@pytest.mark.asyncio
async def test_audit_logger_emit_kafka_pipeline(monkeypatch):
    """Test Kafka Producer logic in AuditLogger."""
    logger = AuditLogger()
    mock_producer = AsyncMock()
    logger.producer = mock_producer
    
    logger.emit(
        action="test_action",
        tenant_id=1,
        user_id=2,
        trace_id="test-trace",
        details={"key": "val"}
    )
    
    # Sleep briefly to let the create_task run
    import asyncio
    await asyncio.sleep(0.01)
    
    mock_producer.send_and_wait.assert_called_once()
    args = mock_producer.send_and_wait.call_args.args
    kwargs = mock_producer.send_and_wait.call_args.kwargs
    
    assert args[0] == "soc_audit_log"
    assert kwargs["key"] == b"1"
    event = json.loads(kwargs["value"].decode('utf-8'))
    assert event["tenant_id"] == 1
    assert event["action"] == "test_action"
    assert event["user_id"] == 2
    assert event["trace_id"] == "test-trace"
    assert event["details"] == {"key": "val"}
    assert "timestamp" in event

@pytest.mark.asyncio
async def test_audit_consumer_postgres_sink_rls_isolation(monkeypatch):
    """Test RLS isolation in AuditConsumer."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session_local = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session
    
    monkeypatch.setattr("app.infrastructure.audit_consumer.AsyncSessionLocal", mock_session_local)
    
    consumer = AuditConsumer()
    event_data = {
        "user_id": 42,
        "trace_id": "test-trace",
        "action": "test_action",
        "details": {},
        "integrity_hash": "test-hash"
    }
    
    await consumer._sink_to_postgres(tenant_id=1, event_data=event_data)
    
    # Ensure RLS statement was executed safely
    executed_statements = [call.args[0].text for call in mock_session.execute.call_args_list]
    assert "SELECT set_config('rls.tenant_id', :tid, true);" in executed_statements[0]
    
    first_call_args = mock_session.execute.call_args_list[0].args
    first_call_kwargs = mock_session.execute.call_args_list[0].kwargs
    if len(first_call_args) > 1:
        assert first_call_args[1] == {"tid": "1"}
    elif "params" in first_call_kwargs:
        assert first_call_kwargs["params"] == {"tid": "1"}
    
    mock_session.add.assert_called_once()
    added_event = mock_session.add.call_args.args[0]
    assert isinstance(added_event, AuditEvent)
    assert added_event.tenant_id == 1
    assert added_event.action == "test_action"
    assert added_event.integrity_hash == "test-hash"
    
    mock_session.commit.assert_called_once()
