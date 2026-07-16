import pytest
import datetime
from unittest.mock import patch, AsyncMock, MagicMock
from connectors.siem.elastic import ElasticConnector
from connectors.siem.graylog import GraylogConnector
from connectors.siem.security_onion import SecurityOnionConnector
from connectors.siem.splunk import SplunkConnector
from connectors.siem.sentinel import SentinelConnector

@pytest.fixture
def dummy_time():
    return datetime.datetime.now(datetime.timezone.utc)

@pytest.mark.asyncio
async def test_elastic_connector(dummy_time):
    connector = ElasticConnector("tenant1", "http://elastic", "key")
    await connector.connect()
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        await connector.authenticate()
    
    with patch.object(connector, 'fetch_events', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"_id": "e1", "event": {"action": "alert", "severity": "high"}}]
        events = await connector.fetch_events(dummy_time)
        assert len(events) == 1
        
        normalized = await connector.normalize(events[0])
        assert normalized.__class__.__name__ == "SecurityEvent"
        assert normalized.event_id == "e1"
        assert normalized.severity == "HIGH"
        assert normalized.source == "elastic_siem"
        assert normalized.tenant_id == "tenant1"
        
    await connector.disconnect()

@pytest.mark.asyncio
async def test_graylog_connector(dummy_time):
    connector = GraylogConnector("tenant1", "http://graylog", "token")
    await connector.connect()
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        await connector.authenticate()
    
    with patch.object(connector, 'fetch_events', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"id": "g1", "message": "auth_fail", "level": "critical"}]
        events = await connector.fetch_events(dummy_time)
        assert len(events) == 1
        
        normalized = await connector.normalize(events[0])
        assert normalized.__class__.__name__ == "SecurityEvent"
        assert normalized.event_id == "g1"
        assert normalized.severity == "CRITICAL"
        assert normalized.source == "graylog"
        assert normalized.tenant_id == "tenant1"
        
    await connector.disconnect()

@pytest.mark.asyncio
async def test_security_onion_connector(dummy_time):
    connector = SecurityOnionConnector("tenant1")
    await connector.connect()
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        await connector.authenticate()
    
    with patch.object(connector, 'fetch_events', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"alert_id": "so1", "rule_name": "malware", "severity_label": "high", "ts": dummy_time.isoformat()}]
        events = await connector.fetch_events(dummy_time)
        assert len(events) == 1
        
        normalized = await connector.normalize(events[0])
        assert normalized.__class__.__name__ == "SecurityEvent"
        assert normalized.event_id == "so1"
        assert normalized.severity == "HIGH"
        assert normalized.source == "security_onion"

    await connector.disconnect()

@pytest.mark.asyncio
async def test_splunk_connector(dummy_time):
    connector = SplunkConnector("tenant1")
    await connector.connect()
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        await connector.authenticate()
    
    with patch.object(connector, 'fetch_events', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"id": "sp1", "source_type": "splunk_alert", "risk_score": 90, "timestamp": dummy_time.isoformat()}]
        events = await connector.fetch_events(dummy_time)
        assert len(events) == 1
        
        normalized = await connector.normalize(events[0])
        assert normalized.__class__.__name__ == "SecurityEvent"
        assert normalized.event_id == "sp1"
        assert normalized.severity == "HIGH"
        assert normalized.source == "splunk"

    await connector.disconnect()

class MockResponse:
    def __init__(self, json_data):
        self._json_data = json_data
    async def json(self):
        return self._json_data
    def raise_for_status(self):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

@pytest.mark.asyncio
async def test_sentinel_connector(dummy_time):
    connector = SentinelConnector("tenant1", "client_id", "client_secret", "workspace_id")
    
    mock_session = MagicMock()
    mock_session.close = AsyncMock()
    
    def side_effect(*args, **kwargs):
        if "oauth2" in args[0]:
            return MockResponse({"access_token": "fake_token"})
        else:
            return MockResponse({
                "tables": [{
                    "columns": [{"name": "IncidentNumber"}, {"name": "Severity"}, {"name": "Title"}, {"name": "TimeGenerated"}],
                    "rows": [["12345", "High", "Suspicious login", dummy_time.isoformat()]]
                }]
            })
            
    mock_session.post.side_effect = side_effect
    
    with patch('aiohttp.ClientSession', return_value=mock_session):
        await connector.connect()
        await connector.authenticate()
        
        events = await connector.fetch_events(dummy_time)
        assert len(events) == 1
        assert events[0]["IncidentNumber"] == "12345"
        
        normalized = await connector.normalize(events[0])
        assert normalized.__class__.__name__ == "SecurityEvent"
        assert normalized.event_id == "12345"
        assert normalized.severity == "HIGH"
        assert normalized.source == "sentinel"
        
        health = await connector.health()
        assert health["status"] == "healthy"
        
        await connector.disconnect()
