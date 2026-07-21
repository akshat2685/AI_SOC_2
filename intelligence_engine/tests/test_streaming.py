import pytest
from fastapi.testclient import TestClient
from intelligence_engine.api.routes.reports import router as reports_router
from intelligence_engine.api.routes.alerts import router as alerts_router
from fastapi import FastAPI

app = FastAPI()
app.include_router(reports_router)
app.include_router(alerts_router)

client = TestClient(app)

def test_reports_digest():
    response = client.get("/reports/digest?period=week")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    content = response.content
    assert b"%PDF-1.4" in content
    assert b"EDYSOR-X Security Digest" in content

def test_reports_audit_alerts():
    response = client.get("/reports/audit-alerts-24h")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    content = response.json()
    assert "report_generated_at" in content
    assert "total_alerts_24h" in content
    assert "alerts" in content

def test_alerts_report_pdf():
    response = client.get("/alerts/101/report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    content = response.content
    assert b"%PDF-1.4" in content
    assert b"EDYSOR-X Alert Report (ID: 101)" in content
