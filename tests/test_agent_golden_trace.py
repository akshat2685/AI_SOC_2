import pytest
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class AgentToolCall(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result_status: str

class IncidentInvestigationTrace(BaseModel):
    incident_id: str
    severity: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    blast_radius: List[str]
    tool_calls: List[AgentToolCall]
    recommended_action: str

# Golden benchmark dataset for agent evaluation
GOLDEN_DATASET = [
    {
        "input_prompt": "Detect suspicious PowerShell process downloading remote payload on endpoint WS-001",
        "expected_severity": "CRITICAL",
        "expected_tools": ["query_endpoint_telemetry", "check_threat_intel_hash", "isolate_host"],
        "simulated_output": {
            "incident_id": "inc-gold-001",
            "severity": "CRITICAL",
            "confidence_score": 0.95,
            "blast_radius": ["WS-001", "DomainController-01"],
            "tool_calls": [
                {"tool_name": "query_endpoint_telemetry", "arguments": {"hostname": "WS-001"}, "result_status": "success"},
                {"tool_name": "check_threat_intel_hash", "arguments": {"sha256": "a" * 64}, "result_status": "malicious"},
                {"tool_name": "isolate_host", "arguments": {"hostname": "WS-001"}, "result_status": "success"}
            ],
            "recommended_action": "Isolate host WS-001 and revoke active Kerberos tickets"
        }
    },
    {
        "input_prompt": "Multiple failed SSH login attempts from IP 198.51.100.22",
        "expected_severity": "HIGH",
        "expected_tools": ["lookup_ip_reputation", "block_ip_firewall"],
        "simulated_output": {
            "incident_id": "inc-gold-002",
            "severity": "HIGH",
            "confidence_score": 0.88,
            "blast_radius": ["Bastion-01"],
            "tool_calls": [
                {"tool_name": "lookup_ip_reputation", "arguments": {"ip": "198.51.100.22"}, "result_status": "high_risk"},
                {"tool_name": "block_ip_firewall", "arguments": {"ip": "198.51.100.22"}, "result_status": "success"}
            ],
            "recommended_action": "Block source IP 198.51.100.22 on edge WAF"
        }
    }
]

def test_golden_dataset_schema_validation():
    """Verify that all golden traces conform to IncidentInvestigationTrace Pydantic schema."""
    for entry in GOLDEN_DATASET:
        trace_data = entry["simulated_output"]
        parsed_trace = IncidentInvestigationTrace(**trace_data)
        
        assert parsed_trace.incident_id.startswith("inc-gold-")
        assert 0.0 <= parsed_trace.confidence_score <= 1.0
        assert len(parsed_trace.tool_calls) > 0

def test_agent_tool_sequence_invariants():
    """Verify that agent golden traces call expected tools in valid sequence."""
    for entry in GOLDEN_DATASET:
        expected_tools = entry["expected_tools"]
        actual_tools = [tc["tool_name"] for tc in entry["simulated_output"]["tool_calls"]]
        
        for expected_tool in expected_tools:
            assert expected_tool in actual_tools, f"Missing expected tool {expected_tool} in trace"

def test_confidence_score_normalization():
    """Verify confidence score bounds and non-empty blast radius on critical alerts."""
    for entry in GOLDEN_DATASET:
        output = entry["simulated_output"]
        if output["severity"] == "CRITICAL":
            assert output["confidence_score"] >= 0.90
            assert len(output["blast_radius"]) >= 1
