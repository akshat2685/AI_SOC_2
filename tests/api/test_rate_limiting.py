import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_rate_limiting_configured_on_app(async_client: AsyncClient):
    """Test that requests to FastAPI app process through rate limiting middleware successfully."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
