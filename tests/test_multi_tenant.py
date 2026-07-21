import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.domain.models import Tenant, User, Asset, RoleEnum, CriticalityEnum
from app.domain.schemas import TenantCreate, UserCreate, AssetCreate
from app.infrastructure.repositories import TenantRepository, UserRepository, AssetRepository
from app.core.security import create_access_token
from app.api.deps import get_current_user, require_roles, TokenData

class TestMultiTenantModels:
    def test_tenant_model(self):
        tenant = Tenant(id=1, name="Acme Corp")
        assert tenant.name == "Acme Corp"
        assert tenant.id == 1

    def test_user_model(self):
        user = User(id=1, tenant_id=1, email="admin@acme.com", role=RoleEnum.TENANT_ADMIN)
        assert user.tenant_id == 1
        assert user.role == RoleEnum.TENANT_ADMIN
        assert user.email == "admin@acme.com"

    def test_asset_model(self):
        asset = Asset(id=1, tenant_id=1, hostname="db-server", ip_address="10.0.0.1", asset_type="Server", criticality=CriticalityEnum.HIGH)
        assert asset.tenant_id == 1
        assert asset.hostname == "db-server"

class TestMultiTenantRepositories:
    @pytest.mark.asyncio
    async def test_rls_filtering_in_get(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = User(id=1, tenant_id=1)
        session.execute.return_value = mock_result
        
        repo = UserRepository(session)
        user = await repo.get(id=1, tenant_id=1)
        
        assert session.execute.call_count == 2
        rls_call = session.execute.call_args_list[0]
        assert "SET LOCAL rls.tenant_id" in str(rls_call[0][0])
        assert rls_call[0][1] == {"tenant_id": "1"}
        
        assert user is not None
        assert user.id == 1

    @pytest.mark.asyncio
    async def test_tenant_injection_in_create(self):
        session = AsyncMock()
        repo = AssetRepository(session)
        
        asset_create = AssetCreate(hostname="host1", ip_address="10.0.0.1", asset_type="server", criticality=CriticalityEnum.LOW, tenant_id=1)
        # Override with tenant_id=2
        asset = await repo.create(asset_create, tenant_id=2)
        
        assert session.add.called
        assert session.commit.called
        assert getattr(asset, "tenant_id", None) == 2
        assert asset.hostname == "host1"
        assert session.execute.call_count == 1 # _set_rls is called once
        assert "SET LOCAL rls.tenant_id" in str(session.execute.call_args_list[0][0][0])

    @pytest.mark.asyncio
    async def test_tenant_missing_in_create_raises_error(self):
        session = AsyncMock()
        repo = AssetRepository(session)
        
        # AssetCreate needs a tenant_id to be valid Pydantic, so we use BaseModel mock or dict workaround,
        # but AssetCreate requires it. We can mock it or just pass None to test repository logic.
        # Let's bypass Pydantic validation by mutating after creation
        asset_create = AssetCreate(hostname="host1", ip_address="10.0.0.1", asset_type="server", criticality=CriticalityEnum.LOW, tenant_id=1)
        asset_create.tenant_id = None
        
        with pytest.raises(ValueError, match="tenant_id is required"):
            await repo.create(asset_create, tenant_id=None)

    @pytest.mark.asyncio
    async def test_tenant_stripped_in_update(self):
        from app.domain.schemas import AssetUpdate
        session = AsyncMock()
        repo = AssetRepository(session)
        
        db_asset = Asset(id=1, tenant_id=1, hostname="host1", ip_address="10.0.0.1", asset_type="server", criticality=CriticalityEnum.LOW)
        # Assuming AssetUpdate doesn't even have tenant_id normally, but if it did or we pass a dict:
        class FakeAssetUpdate(AssetUpdate):
            tenant_id: int = 5
        
        update_schema = FakeAssetUpdate(hostname="host2", tenant_id=5)
        
        updated_asset = await repo.update(db_asset, update_schema, tenant_id=1)
        assert updated_asset.tenant_id == 1 # Unchanged!
        assert updated_asset.hostname == "host2"
        assert session.execute.call_count == 1


class TestMultiTenantSecurity:
    def test_create_access_token_includes_tenant(self):
        token = create_access_token(subject=1, role=RoleEnum.TENANT_ADMIN, tenant_id=5)
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self):
        token = create_access_token(subject=1, role=RoleEnum.TENANT_ADMIN, tenant_id=5)
        
        token_data = await get_current_user(token=token)
        assert token_data.user_id == 1
        assert token_data.role == RoleEnum.TENANT_ADMIN
        assert token_data.tenant_id == 5

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(token="invalid.token.here")
        assert exc.value.status_code == 403

    def test_require_roles_success(self):
        token_data = TokenData(user_id=1, role=RoleEnum.TENANT_ADMIN, tenant_id=1)
        checker = require_roles([RoleEnum.TENANT_ADMIN])
        result = checker(current_user=token_data)
        assert result.user_id == 1

    def test_require_roles_forbidden(self):
        token_data = TokenData(user_id=1, role=RoleEnum.TENANT_VIEWER, tenant_id=1)
        checker = require_roles([RoleEnum.TENANT_ADMIN])
        with pytest.raises(HTTPException) as exc:
            checker(current_user=token_data)
        assert exc.value.status_code == 403
