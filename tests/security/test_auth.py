import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_invalid_credentials(async_client: AsyncClient):
    """Test login with non-existent user returns 401 Unauthorized."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "nonexistent@example.com", "password": "wrong_password"}
    )
    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]
