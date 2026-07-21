import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

class MockPackage(MagicMock):
    __path__ = []
    __spec__ = None
mock_sklearn = MockPackage()
sys.modules['sklearn'] = mock_sklearn
sys.modules['sklearn.ensemble'] = MagicMock()
sys.modules['sklearn.pipeline'] = MagicMock()
sys.modules['sklearn.preprocessing'] = MagicMock()
sys.modules['sklearn.impute'] = MagicMock()
sys.modules['sklearn.compose'] = MagicMock()

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'api')))

def fake_require_permission(perm):
    def fake_dep():
        return {"identity": "test_user", "tenant_id": "test_tenant", "roles": ["super_admin"], "permissions": ["read", "write", "manage_settings", "execute"]}
    return fake_dep

try:
    import intelligence_engine.api.services.security
    intelligence_engine.api.services.security.require_permission = fake_require_permission
    import intelligence_engine.api.middleware.auth
    intelligence_engine.api.middleware.auth.require_permission = fake_require_permission
except ImportError:
    pass

try:
    import api.services.security
    api.services.security.require_permission = fake_require_permission
    import api.middleware.auth
    api.middleware.auth.require_permission = fake_require_permission
except ImportError:
    pass

from main import app
try:
    from api.main import app as new_app
except ImportError:
    from intelligence_engine.api.main import app as new_app

client = TestClient(app)
new_client = TestClient(new_app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "intelligence-engine"}

def test_copilot_query():
    try:
        from main import llm
    except ImportError:
        from intelligence_engine.main import llm
    mock_response = MagicMock()
    mock_response.content = '{"answer": "Test Answer", "evidence": ["Test Evidence"], "confidence": 0.99, "sources": ["Test Source"], "mitre_mapping": ["T1234"]}'
    original_ainvoke = llm.ainvoke
    async def mock_ainvoke(*args, **kwargs):
        return mock_response
    object.__setattr__(llm, "ainvoke", mock_ainvoke)
    try:

        response = client.post("/api/v1/copilot/query", json={"query": "Test query"})
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Test Answer"
        assert "Test Evidence" in data["evidence"]
        assert data["confidence"] == 0.99
        assert "Test Source" in data["sources"]
        assert "T1234" in data["mitre_mapping"]
    finally:
        object.__setattr__(llm, "ainvoke", original_ainvoke)

def test_investigation_explain():
    try:
        from main import llm
    except ImportError:
        from intelligence_engine.main import llm
    mock_response = MagicMock()
    mock_response.content = '{"timeline": ["09:00: Event"], "root_cause": "Test Cause", "impact": "Test Impact", "recommendations": ["Test Rec"]}'
    original_ainvoke = llm.ainvoke
    async def mock_ainvoke(*args, **kwargs):
        return mock_response
    object.__setattr__(llm, "ainvoke", mock_ainvoke)
    try:

        response = client.post("/api/v1/investigation/explain", json={"investigation_id": "INV-123"})
        assert response.status_code == 200
        data = response.json()
        assert "09:00: Event" in data["timeline"]
        assert data["root_cause"] == "Test Cause"
        assert data["impact"] == "Test Impact"
        assert "Test Rec" in data["recommendations"]
    finally:
        object.__setattr__(llm, "ainvoke", original_ainvoke)

# New API Tests for Milestone 2 Router Framework
def test_new_health_check():
    response = new_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["overall"] in ["healthy", "unhealthy"]

def test_new_copilot_query():
    response = new_client.post("/api/v1/copilot/query", json={"query": "hello"})
    assert response.status_code == 200
    assert "answer" in response.json()

def test_new_investigate():
    response = new_client.post("/api/v1/investigations/investigate?alert_id=ALT-999")
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

def test_new_explain():
    response = new_client.post("/api/v1/investigations/explain", json={"investigation_id": "INV-999"})
    assert response.status_code == 200
    assert "root_cause" in response.json()

def test_new_alerts():
    response = new_client.get("/api/v1/alerts")
    assert response.status_code == 200
    assert "alerts" in response.json()

def test_new_connector_status():
    response = new_client.get("/api/v1/connectors/status")
    assert response.status_code == 200
    assert "neo4j" in response.json()

def test_new_playbooks():
    response = new_client.get("/api/v1/playbooks/approvals")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_new_reports():
    response = new_client.get("/api/v1/reports/digest")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")

def test_new_reports_audit():
    response = new_client.get("/api/v1/reports/audit-alerts-24h")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert "alerts" in response.json()

def test_new_dashboard():
    response = new_client.get("/api/v1/dashboard/risk-heatmap")
    assert response.status_code == 200
    assert "heatmap" in response.json()

def test_chat():
    response = new_client.post("/chat", json={"query": "test query"})
    assert response.status_code == 200
    assert "response" in response.json()
    
    response2 = new_client.post("/api/v1/chat", json={"query": "test query"})
    assert response2.status_code == 200
    assert "response" in response2.json()

@patch("api.database.db.execute_postgres")
def test_incidents(mock_db):
    mock_db.side_effect = Exception("DB Down")
    response = new_client.get("/api/v1/incidents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    
    response = new_client.get("/api/v1/incidents/1/details")
    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert "logs" in response.json()
    
    response = new_client.get("/api/v1/incidents/1/predict-risk")
    assert response.status_code == 200
    assert "riskScore" in response.json()
    
    response = new_client.get("/api/v1/incidents/1/recommended-triage")
    assert response.status_code == 200
    assert "recommendedPlaybooks" in response.json()
    
    response = new_client.put("/api/v1/incidents/1", json={"status": "CLOSED", "verdict": "FALSE_POSITIVE"})
    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"
    assert response.json()["verdict"] == "FALSE_POSITIVE"
    
    response = new_client.post("/api/v1/incidents/1/verdict", json={"verdict": "TRUE_POSITIVE", "notes": "Confirmed malicious activity."})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["incident"]["verdict"] == "TRUE_POSITIVE"
    
    response = new_client.get("/api/v1/incidents/1/graph")
    assert response.status_code == 200
    assert "nodes" in response.json()

def test_connectors_and_threat_intel():
    response = new_client.post("/api/v1/integrations/sync")
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    response = new_client.get("/threat-intel/cve/CVE-2026-9999")
    assert response.status_code == 200
    assert response.json()["cve_id"] == "CVE-2026-9999"
    
    response = new_client.get("/threat-intel/ip/1.1.1.1")
    assert response.status_code == 200
    assert response.json()["ip"] == "1.1.1.1"
    
    response = new_client.post("/threat-intel/sync")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    response = new_client.post("/threat-intel/kev/sync")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    response = new_client.get("/threat-intel/report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"

def test_approvals_and_firewall():
    response = new_client.get("/approvals")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    
    response = new_client.post("/approvals/1", json={"status": "APPROVED", "human_feedback": "Proceed with block"})
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    response = new_client.post("/api/v1/firewall/block", json={"ip": "1.1.1.1", "reason": "DDoS target"})
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    response = new_client.post("/api/v1/firewall/unblock", json={"ip": "1.1.1.1"})
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_executive_dashboard_and_stats():
    response = new_client.get("/stats")
    assert response.status_code == 200
    assert "incidents" in response.json()
    
    response = new_client.get("/api/v1/executive/metrics")
    assert response.status_code == 200
    assert "mttd" in response.json()
    
    response = new_client.get("/api/risk-heatmap")
    assert response.status_code == 200
    assert "heatmap" in response.json()

def test_trace_id_injection_and_headers(caplog):
    import logging
    try:
        from core.logging_config import JSONFormatter
    except ImportError:
        from intelligence_engine.core.logging_config import JSONFormatter

    formatter = JSONFormatter()

    with caplog.at_level(logging.INFO):
        # 1. Incoming request triggers trace ID generation, response header contains X-Request-ID
        response = new_client.get("/api/v1/health")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        trace_id = response.headers["X-Request-ID"]
        assert len(trace_id) > 0

        # Check logs output contains the trace_id
        trace_records = [r for r in caplog.records if r.name.startswith("api.middleware.trace")]
        assert len(trace_records) > 0
        
        # Format the log record and assert it contains trace_id
        try:
            from core.logging_config import trace_id_var
        except ImportError:
            from intelligence_engine.core.logging_config import trace_id_var
        token = trace_id_var.set(trace_id)
        formatted_json = formatter.format(trace_records[0])
        trace_id_var.reset(token)
        import json
        log_obj = json.loads(formatted_json)
        assert log_obj["trace_id"] == trace_id

def test_trace_id_extraction_from_headers():
    custom_trace_id = "test-custom-trace-id-12345"
    response = new_client.get("/api/v1/health", headers={"X-Request-ID": custom_trace_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_trace_id

def test_global_exception_handler(caplog):
    import logging
    try:
        from core.logging_config import JSONFormatter
    except ImportError:
        from intelligence_engine.core.logging_config import JSONFormatter

    formatter = JSONFormatter()

    with caplog.at_level(logging.ERROR):
        # Triggers unhandled exception in trigger-error route
        response = new_client.get("/api/v1/trigger-error")
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal server error"
        assert "trace_id" in data
        trace_id = data["trace_id"]
        assert response.headers.get("X-Request-ID") == trace_id

        # Check that exception logs contain the trace ID
        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_records) > 0
        
        # Format the log record and assert it contains trace_id
        try:
            from core.logging_config import trace_id_var
        except ImportError:
            from intelligence_engine.core.logging_config import trace_id_var
        token = trace_id_var.set(trace_id)
        formatted_json = formatter.format(error_records[0])
        trace_id_var.reset(token)
        import json
        log_obj = json.loads(formatted_json)
        assert log_obj["trace_id"] == trace_id

# Edge cases, boundary, and stress tests added by teamwork_preview_challenger_1
def test_invalid_path_param_types_validation():
    # Alerts endpoints expect integer IDs. Passing string should result in 422 Unprocessable Entity
    response = new_client.get("/api/v1/alerts/invalid-string-id")
    assert response.status_code == 422
    assert "type_error.integer" in response.text or "int_parsing" in response.text

    response = new_client.post("/api/v1/alerts/invalid-string-id/investigate")
    assert response.status_code == 422

    response = new_client.get("/api/v1/alerts/invalid-string-id/report.pdf")
    assert response.status_code == 422

def test_missing_body_elements_validation():
    # POST /api/v1/copilot/query requires a query field
    response = new_client.post("/api/v1/copilot/query", json={})
    assert response.status_code == 422
    assert "field required" in response.text.lower() or "missing" in response.text.lower()

    # POST /api/v1/investigations/explain requires investigation_id
    response = new_client.post("/api/v1/investigations/explain", json={})
    assert response.status_code == 422

    # POST /api/v1/playbooks/approvals/{id} requires status
    response = new_client.post("/api/v1/playbooks/approvals/1", json={})
    assert response.status_code == 422

    # POST /api/v1/firewall/block requires ip
    response = new_client.post("/api/v1/firewall/block", json={})
    assert response.status_code == 422

def test_non_existent_route():
    # Requesting an undefined endpoint should return 404
    response = new_client.get("/api/v1/non-existent-route-path")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}

def test_incident_not_found():
    # Getting or updating non-existent incident ID should raise 404
    response = new_client.get("/api/v1/incidents/non-existent-id")
    assert response.status_code == 404
    assert "Incident not found" in response.json()["detail"]

def test_invalid_http_method():
    # Testing endpoint with wrong HTTP method should yield 405 Method Not Allowed
    response = new_client.post("/api/v1/health")
    assert response.status_code == 405
    assert "method not allowed" in response.text.lower() or "Method Not Allowed" in response.text

def test_openapi_docs():
    # Requesting "/docs" from the new_client returns status code 200 and contains HTML.
    response_docs = new_client.get("/docs")
    assert response_docs.status_code == 200
    assert "text/html" in response_docs.headers.get("content-type", "").lower()
    assert "<html" in response_docs.text.lower()

    # Requesting "/openapi.json" from the new_client returns status code 200 and contains JSON schema.
    response_openapi = new_client.get("/openapi.json")
    assert response_openapi.status_code == 200
    assert "application/json" in response_openapi.headers.get("content-type", "").lower()
    openapi_data = response_openapi.json()
    assert "openapi" in openapi_data
    assert "info" in openapi_data
    assert "paths" in openapi_data




