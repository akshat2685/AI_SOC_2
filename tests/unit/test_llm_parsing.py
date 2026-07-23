import pytest
from pydantic import ValidationError
from intelligence_engine.agents.soc_orchestrator import (
    ThreatIntelResponse,
    RiskScoringResponse,
    ResponsePlanResponse
)

def test_threat_intel_response_valid():
    data = {
        "indicators": ["192.168.1.1", "malicious.domain.com"],
        "confidence": "high",
        "threat_type": "ransomware",
        "summary": "High risk activity detected"
    }
    obj = ThreatIntelResponse(**data)
    assert obj.confidence == "high"
    assert len(obj.indicators) == 2

def test_threat_intel_response_defaults():
    obj = ThreatIntelResponse()
    assert obj.confidence == "low"
    assert obj.threat_type == "unknown"
    assert obj.indicators == []

def test_risk_scoring_response_validation():
    data = {"risk_score": 85.5, "severity_score": 90, "rationale": "Critical anomaly"}
    obj = RiskScoringResponse(**data)
    assert obj.risk_score == 85.5
    assert obj.severity_score == 90

def test_risk_scoring_out_of_bounds():
    with pytest.raises(ValidationError):
        RiskScoringResponse(risk_score=150.0, severity_score=50, rationale="Invalid")

def test_response_plan_response_valid():
    data = {
        "actions": ["isolate_host", "block_ip"],
        "priority": "critical",
        "estimated_impact": "High containment",
        "playbook_id": "PB-RANSOMWARE-01"
    }
    obj = ResponsePlanResponse(**data)
    assert obj.priority == "critical"
    assert len(obj.actions) == 2
