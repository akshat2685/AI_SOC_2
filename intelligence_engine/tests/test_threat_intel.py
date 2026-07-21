import pytest
import sys
from unittest.mock import MagicMock, patch, AsyncMock
import datetime
import json

# Mock external dependencies for ingestors
sys.modules['pymisp'] = MagicMock()
sys.modules['taxii2client'] = MagicMock()
sys.modules['taxii2client.v21'] = MagicMock()
sys.modules['stix2'] = MagicMock()

import os
os.environ["POSTGRES_URL"] = "postgresql://user:password@localhost/db"
os.environ["NEO4J_AUTH"] = "neo4j/password"
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
os.environ["SECRET_KEY"] = "secret"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["QDRANT_URL"] = "http://localhost:6333"

# Now import the modules
from intelligence_engine.threat_intel.models.pg_models import ThreatFeed, Indicator
from intelligence_engine.threat_intel.processing.distribution_engine import DistributionEngine
from intelligence_engine.threat_intel.ingestors.base_ingestor import BaseIngestor
from intelligence_engine.threat_intel.ingestors.misp_ingestor import MISPIngestor
from intelligence_engine.threat_intel.ingestors.taxii_ingestor import TAXIIIngestor


def test_threat_feed_model():
    feed = ThreatFeed(
        id="feed-1",
        name="Test Feed",
        url="http://test-feed.com",
        description="A test feed",
        provider="Test Provider",
        is_active=True
    )
    assert feed.id == "feed-1"
    assert feed.name == "Test Feed"
    assert feed.url == "http://test-feed.com"
    assert feed.provider == "Test Provider"
    assert feed.is_active is True


def test_indicator_model():
    now = datetime.datetime.now(datetime.timezone.utc)
    indicator = Indicator(
        id="ind-1",
        feed_id="feed-1",
        indicator_type="ipv4",
        indicator_value="192.168.1.1",
        confidence=80,
        severity="high",
        valid_from=now
    )
    assert indicator.id == "ind-1"
    assert indicator.feed_id == "feed-1"
    assert indicator.indicator_type == "ipv4"
    assert indicator.indicator_value == "192.168.1.1"
    assert indicator.confidence == 80
    assert indicator.severity == "high"


@pytest.mark.asyncio
@patch('intelligence_engine.threat_intel.processing.distribution_engine.create_event_bus')
@patch('intelligence_engine.threat_intel.processing.distribution_engine.db')
async def test_distribution_engine(mock_db, mock_create_event_bus):
    mock_event_bus = AsyncMock()
    mock_create_event_bus.return_value = mock_event_bus
    mock_redis = MagicMock()
    mock_db.get_redis_client.return_value = mock_redis

    engine = DistributionEngine(use_kafka=True)
    assert engine.event_bus == mock_event_bus
    assert engine.redis_client == mock_redis

    indicators = [
        {
            "tenant_id": "tenant-1",
            "indicator_type": "ipv4",
            "indicator_value": "10.0.0.1",
            "confidence": 90
        },
        {
            "tenant_id": "tenant-1",
            "indicator_type": "domain",
            "indicator_value": "malicious.com",
            "confidence": 100
        }
    ]

    await engine.distribute(indicators)

    assert mock_event_bus.publish.call_count == 2
    mock_event_bus.publish.assert_any_call("threat.intel.ingested", indicators[0])
    mock_event_bus.publish.assert_any_call("threat.intel.ingested", indicators[1])

    assert mock_redis.setex.call_count == 2
    expected_key_1 = "ti:tenant-1:ipv4:10.0.0.1"
    mock_redis.setex.assert_any_call(expected_key_1, 604800, json.dumps(indicators[0]))
    expected_key_2 = "ti:tenant-1:domain:malicious.com"
    mock_redis.setex.assert_any_call(expected_key_2, 604800, json.dumps(indicators[1]))


def test_base_ingestor():
    with pytest.raises(TypeError):
        # Cannot instantiate abstract class
        BaseIngestor(tenant_id="tenant-1")


@patch('intelligence_engine.threat_intel.ingestors.misp_ingestor.ExpandedPyMISP')
def test_misp_ingestor(mock_expanded_pymisp):
    mock_misp_instance = MagicMock()
    mock_expanded_pymisp.return_value = mock_misp_instance
    
    mock_misp_instance.search.return_value = [
        {
            'Event': {
                'id': '1234',
                'Attribute': [
                    {'type': 'ip-src', 'value': '1.1.1.1'},
                    {'type': 'domain', 'value': 'bad-domain.com'}
                ]
            }
        }
    ]

    ingestor = MISPIngestor(tenant_id="tenant-1", url="http://misp.local", key="dummy-key")
    
    raw_data = ingestor.fetch_data()
    assert len(raw_data) == 1
    
    indicators = ingestor.parse_data(raw_data)
    assert len(indicators) == 2
    assert indicators[0]['feed_id'] == "misp_1234"
    assert indicators[0]['indicator_type'] == "ip-src"
    assert indicators[0]['indicator_value'] == "1.1.1.1"
    assert indicators[0]['tenant_id'] == "tenant-1"
    
    assert indicators[1]['indicator_type'] == "domain"
    assert indicators[1]['indicator_value'] == "bad-domain.com"


@patch('intelligence_engine.threat_intel.ingestors.taxii_ingestor.stix2')
@patch('intelligence_engine.threat_intel.ingestors.taxii_ingestor.Collection')
def test_taxii_ingestor(mock_collection_class, mock_stix2):
    mock_collection_instance = MagicMock()
    mock_collection_instance.id = "col-5678"
    mock_collection_class.return_value = mock_collection_instance
    
    mock_collection_instance.get_objects.return_value = {
        "objects": [
            {"type": "indicator", "pattern": "[ipv4-addr:value = '2.2.2.2']"}
        ]
    }
    
    mock_stix2.parse.return_value = {
        "type": "indicator",
        "pattern_type": "stix",
        "pattern": "[ipv4-addr:value = '2.2.2.2']",
        "valid_from": "2023-01-01T00:00:00Z"
    }

    ingestor = TAXIIIngestor(tenant_id="tenant-1", collection_url="http://taxii.local/collection/1")
    
    raw_data = ingestor.fetch_data()
    assert len(raw_data) == 1
    
    indicators = ingestor.parse_data(raw_data)
    assert len(indicators) == 1
    assert indicators[0]['feed_id'] == "taxii_col-5678"
    assert indicators[0]['indicator_type'] == "stix"
    assert indicators[0]['indicator_value'] == "[ipv4-addr:value = '2.2.2.2']"
    assert indicators[0]['tenant_id'] == "tenant-1"
