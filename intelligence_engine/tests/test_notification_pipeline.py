import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
import json

from intelligence_engine.core.ws_manager import ConnectionManager
from intelligence_engine.core.notification_router import NotificationRouter
from intelligence_engine.core.webhook_delivery import deliver_webhook
from intelligence_engine.core.crypto import envelope_crypto
from intelligence_engine.kafka_consumer import process_batch_with_retry

# 1. WebSocket Auth / Isolation
@pytest.mark.asyncio
async def test_websocket_auth_and_isolation():
    manager = ConnectionManager()
    manager.redis_client = AsyncMock()
    
    # Mock JWT decode
    with patch("intelligence_engine.core.ws_manager.jwt.decode") as mock_jwt_decode:
        # Valid token for tenant 1
        mock_jwt_decode.return_value = {"tenant_id": 1}
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        tenant1 = await manager.connect(ws1, "valid_token_1")
        assert tenant1 == 1
        assert ws1 in manager.active_connections[1]
        
        # Verify JWT signature verification is enabled
        call_kwargs = mock_jwt_decode.call_args[1]
        assert call_kwargs.get("options", {}).get("verify_signature") is True
        
        # Valid token for tenant 2
        mock_jwt_decode.return_value = {"tenant_id": 2}
        ws2 = AsyncMock()
        ws2.accept = AsyncMock()
        tenant2 = await manager.connect(ws2, "valid_token_2")
        assert tenant2 == 2
        assert ws2 in manager.active_connections[2]
        
        # Invalid token (no tenant_id)
        mock_jwt_decode.return_value = {}
        ws_invalid = AsyncMock()
        ws_invalid.accept = AsyncMock()
        ws_invalid.close = AsyncMock()
        tenant_invalid = await manager.connect(ws_invalid, "invalid_token")
        assert tenant_invalid is None
        ws_invalid.close.assert_called_with(code=4001, reason="Invalid token: missing tenant_id")

# 2. Webhook HMAC & Retry
@pytest.mark.asyncio
async def test_webhook_hmac_and_retry():
    with patch("intelligence_engine.core.webhook_delivery.httpx.AsyncClient.post") as mock_post:
        # Mocking to fail once then succeed
        mock_post.side_effect = [Exception("Network error"), MagicMock(status_code=200)]
        
        with patch("intelligence_engine.core.webhook_delivery._update_history_status", new_callable=AsyncMock) as mock_update_history:
            with patch("intelligence_engine.core.webhook_delivery.envelope_crypto.decrypt") as mock_decrypt:
                mock_decrypt.return_value = bytearray(b"test_secret")
                await deliver_webhook(1, "https://example.com/webhook", "encrypted_secret", {"alert": "test"}, 10)
            
            # Post should be called twice
            assert mock_post.call_count == 2
            
            # Check headers of the last call for HMAC
            call_kwargs = mock_post.call_args[1]
            headers = call_kwargs["headers"]
            assert "X-Edysor-Signature" in headers
            assert headers["X-Edysor-Signature"].startswith("sha256=")
            
            # Check history updates: retrying -> delivered
            mock_update_history.assert_any_call(10, "retrying", 1, "Network error")
            mock_update_history.assert_any_call(10, "delivered", 2, None)

@pytest.mark.asyncio
async def test_webhook_delivery_fails_on_bad_secret():
    with patch("intelligence_engine.core.webhook_delivery.httpx.AsyncClient.post") as mock_post:
        with patch("intelligence_engine.core.webhook_delivery._update_history_status", new_callable=AsyncMock) as mock_update_history:
            with patch("intelligence_engine.core.webhook_delivery.envelope_crypto.decrypt") as mock_decrypt:
                mock_decrypt.side_effect = Exception("Failed to decrypt")
                # Passing a non-encrypted secret should fail securely
                await deliver_webhook(1, "https://example.com/webhook", "invalid_unencrypted_secret", {"alert": "test"}, 11)
            
            # Post should NOT be called
            assert mock_post.call_count == 0
            
            # Check history updates: failed securely
            mock_update_history.assert_called_once_with(11, "failed", 1, "Failed to decrypt secret")

# 3. Severity Filtering
def test_severity_filtering():
    router = NotificationRouter()
    
    # Should deliver (min_severity = LOW)
    assert router._meets_severity("LOW", "LOW") is True
    assert router._meets_severity("LOW", "CRITICAL") is True
    
    # Should not deliver (min_severity = HIGH, event = MEDIUM)
    assert router._meets_severity("HIGH", "MEDIUM") is False
    
    # Empty event severity -> True
    assert router._meets_severity("HIGH", "") is True

# 4. RLS Isolation (Logical tenant isolation)
@pytest.mark.asyncio
async def test_rls_isolation_in_router():
    router = NotificationRouter()
    
    with patch("intelligence_engine.core.notification_router.SessionLocal") as mock_session_local:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        
        # Mock database returning preferences for tenant 1
        mock_session.execute.return_value.mappings.return_value.all.side_effect = [
            [{"id": 1, "channel": "email", "enabled": True, "min_severity": "LOW", "quiet_hours_start": None, "quiet_hours_end": None, "config": ""}],
            []  # webhooks
        ]
        
        with patch.object(router, "_create_history", return_value=1) as mock_create_history:
            with patch("intelligence_engine.core.notification_router.email_sink", new_callable=AsyncMock) as mock_email_sink:
                await router.route(tenant_id=1, event_type="alert", payload={"severity": "HIGH"})
                
                # Verify that tenant_id 1 was used in the query
                mock_email_sink.assert_called_once_with(1, {"severity": "HIGH"}, 1)
                mock_create_history.assert_called_once()
                assert mock_create_history.call_args[0][0] == 1 # tenant_id

# 5. Kafka Consumer Integration
@pytest.mark.asyncio
async def test_kafka_consumer_triggers_notification():
    # When anomaly is detected (label -1), it should call notification_router.route
    with patch("intelligence_engine.kafka_consumer._detection_engine.extract_features") as mock_extract:
        import pandas as pd
        mock_extract.return_value = pd.DataFrame([1]) # Not empty
        
        with patch("intelligence_engine.kafka_consumer._detection_engine.detect_anomalies") as mock_detect:
            # -1 triggers anomaly flow
            mock_detect.return_value = [-1]
            
            with patch("intelligence_engine.kafka_consumer.notification_router.route", new_callable=AsyncMock) as mock_route:
                with patch("intelligence_engine.kafka_consumer.run_orchestrator", new_callable=AsyncMock) as mock_orch:
                    
                    event_batch = [{"tenant_id": 42, "event_id": "test_123", "data": "anomaly"}]
                    await process_batch_with_retry(event_batch, max_retries=0)
                    
                    # Verify route was called for anomaly_detected
                    mock_route.assert_any_call(
                        tenant_id=42,
                        event_type="anomaly_detected",
                        payload={"alert_id": "test_123", "tenant_id": 42, "event_id": "test_123", "data": "anomaly"}
                    )
