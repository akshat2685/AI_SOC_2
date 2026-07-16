import pytest
from datetime import datetime
from intelligence_engine.core.normalization import NormalizationEngine, EventRouter, normalize_event, SecurityEvent

def test_normalization_engine():
    yaml_config = """
mappings:
  source_a:
    event_type: 'type_field'
    severity: 'level.severity'
    timestamp: 'time'
"""
    engine = NormalizationEngine(yaml_config_str=yaml_config)
    
    raw_event = {
        "id": "123",
        "type_field": "login_failed",
        "level": {"severity": "HIGH"},
        "time": "2023-10-10T12:00:00Z",
        "ip": "1.2.3.4"
    }
    
    sec_event = engine.normalize(raw_event, "source_a")
    
    assert sec_event.event_type == "login_failed"
    assert sec_event.severity == "HIGH"
    assert "1.2.3.4" in sec_event.iocs
    assert sec_event.normalized_payload["timestamp"] == "2023-10-10T12:00:00Z"
    assert sec_event.mitre_techniques == ["T1110"]
    assert sec_event.source == "source_a"

def test_event_router():
    router = EventRouter()
    router.add_route(lambda e: e.severity == 'CRITICAL', 'critical_topic')
    
    event = SecurityEvent(
        event_id="1", tenant_id="t1", source="src", event_type="test",
        severity="CRITICAL", timestamp=datetime.utcnow(),
        raw_payload={}, normalized_payload={}
    )
    
    topic = router.route_event(event)
    assert topic == "critical_topic"
    assert event.topic == "critical_topic"

def test_default_normalize_event():
    raw = {"severity": "CRITICAL", "event_type": "unknown"}
    evt = normalize_event(raw, "unknown_source")
    assert evt.topic == "critical_alerts"
    assert evt.severity == "CRITICAL"
