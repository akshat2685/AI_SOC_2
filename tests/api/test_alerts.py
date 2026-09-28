import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.models import Alert, Incident, SeverityEnum, StatusEnum
from app.core.security import create_access_token


def _auth_headers(role: str = "TENANT_ADMIN", user_id: int = 1, tenant_id: int = 1):
    """Mint a real JWT the way the login endpoint does.

    The alerts routes closed public access (401 unauthenticated via
    require_roles_dual), so these tests must authenticate instead of
    asserting the old open-access behavior.
    """
    token = create_access_token(subject=user_id, role=role, tenant_id=tenant_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_alerts_empty(async_client: AsyncClient):
    """Test GET /api/v1/alerts when database is empty."""
    response = await async_client.get("/api/v1/alerts", headers=_auth_headers())
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_alerts_unauthenticated_returns_401(async_client: AsyncClient):
    """Test GET /api/v1/alerts without credentials returns 401 (public access closed)."""
    response = await async_client.get("/api/v1/alerts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_alert_details_not_found(async_client: AsyncClient):
    """Test GET /api/v1/alerts/99999/details returns 404 when alert does not exist."""
    response = await async_client.get("/api/v1/alerts/99999/details", headers=_auth_headers())
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
    # NOTE: patch the module instance the app actually uses (imported as
    # `app.api.v1.alerts` via backend/app/main.py), not the `backend.`-prefixed
    # orphan module path.
    with patch("app.api.v1.alerts.run_orchestrator"):
        response = await async_client.post(
            f"/api/v1/alerts/{alert.id}/investigate", headers=_auth_headers()
        )
        assert response.status_code == 202
        res_data = response.json()
        assert res_data["status"] == "investigation_started"
        assert res_data["alert_id"] == alert.id
