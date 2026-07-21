import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

from app.main import app
from app.api.deps import get_current_user_dual
from app.infrastructure.database import get_db

async def override_get_current_user():
    return 1

app.dependency_overrides[get_current_user_dual] = override_get_current_user

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_list_frameworks(client):
    with patch("app.api.v1.compliance.current_tenant_id") as mock_tenant_id:
        mock_tenant_id.get.return_value = 1
        
        mock_db = AsyncMock()
        mock_result = MagicMock()
        
        class MockFramework:
            id = 1
            name = "SOC2"
            version = "2017"
            description = "SOC 2 Framework"
            
        mock_result.scalars().all.return_value = [MockFramework()]
        mock_db.execute.return_value = mock_result
        
        app.dependency_overrides[get_db] = lambda: mock_db
        
        response = client.get("/api/v1/compliance/frameworks")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "SOC2"

def test_get_posture(client):
    with patch("app.api.v1.compliance.current_tenant_id") as mock_tenant_id:
        mock_tenant_id.get.return_value = 1
        
        mock_db = AsyncMock()
        
        mock_total_controls_result = MagicMock()
        mock_total_controls_result.scalar.return_value = 10
        
        mock_violations_result = MagicMock()
        class MockViolation:
            id = 1
            rule_id = 100
            status = "OPEN"
            from datetime import datetime
            detected_at = datetime.now()
            
        mock_violations_result.scalars().all.return_value = [MockViolation()]
        
        mock_failed_controls_result = MagicMock()
        mock_failed_controls_result.scalar.return_value = 1
        
        # DB execute is called 3 times
        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_total_controls_result
            elif call_count == 2:
                return mock_violations_result
            else:
                return mock_failed_controls_result
                
        call_count = 0
        mock_db.execute = mock_execute
        
        app.dependency_overrides[get_db] = lambda: mock_db
        
        response = client.get("/api/v1/compliance/posture")
        assert response.status_code == 200
        data = response.json()
        assert data["score"] == 90.0
        assert data["total_controls"] == 10
        assert data["failed_controls"] == 1
        assert len(data["violations"]) == 1
