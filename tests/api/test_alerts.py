import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.models import Alert, Incident, SeverityEnum, StatusEnum

@pytest.mark.asyncio
async def test_get_alerts_empty(async_client: AsyncClient):
    """Test GET /api/v1/alerts when database is empty."""
    response = await async_client.get("/api/v1/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_get_alert_details_not_found(async_client: AsyncClient):
    """Test GET /api/v1/alerts/99999/details returns 404 when alert does not exist."""
    response = await async_client.get("/api/v1/alerts/99999/details")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_trigger_investigation_returns_202(
    async_client: AsyncClient,
    test_db_session: AsyncSession
):
    """Test POST /api/v1/alerts/{id}/investigate triggers background task and returns HTTP 202."""
    # Seed alert in DB
    alert = Alert(
        tenant_id=1,
        source="CrowdStrike",
        rule_name="Suspicious Execution",
        description="PowerShell executed encoded payload",
        timestamp=datetime.now(timezone.utc)
    )
    test_db_session.add(alert)
    await test_db_session.commit()
    await test_db_session.refresh(alert)

    # Mock orchestrator
    with patch("backend.app.api.v1.alerts.run_orchestrator"):
        response = await async_client.post(f"/api/v1/alerts/{alert.id}/investigate")
        assert response.status_code == 202
        res_data = response.json()
        assert res_data["status"] == "investigation_started"
        assert res_data["alert_id"] == alert.id
