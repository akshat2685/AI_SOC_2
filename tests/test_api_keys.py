import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import uuid
import sys
import os
import hashlib
from fastapi import Request
from starlette.responses import JSONResponse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.domain.models import ApiKey, Tenant, User, RoleEnum
from app.infrastructure.security import generate_api_key, hash_api_key
from app.api.middleware.auth_middleware import DualAuthMiddleware
from app.core.auth import current_tenant_id, current_user_id, current_api_key

class TestApiKeySecurity:
    def test_generate_api_key(self):
        raw_key, key_prefix, key_hash = generate_api_key()
        assert len(raw_key) > 32
        assert len(key_prefix) == 8
        assert raw_key.startswith(key_prefix)
        assert len(key_hash) == 64
        assert hashlib.sha256(raw_key.encode()).hexdigest() == key_hash

    def test_hash_api_key(self):
        raw_key = "test_key_123"
        hashed = hash_api_key(raw_key)
        assert hashed == hashlib.sha256(raw_key.encode()).hexdigest()

class TestApiKeyModel:
    def test_api_key_model_defaults(self):
        api_key = ApiKey(tenant_id=1, created_by=1, name="Test Key", key_prefix="12345678", key_hash="hash", is_active=True, scopes=[])
        assert api_key.is_active is True
        assert api_key.scopes == []

class TestApiKeyEndpoints:
    @pytest.mark.asyncio
    @patch("app.api.v1.api_keys.get_db")
    async def test_create_api_key_endpoint(self, mock_get_db):
        from app.api.v1.api_keys import create_api_key
        from app.domain.schemas import ApiKeyCreate
        
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        
        async def mock_refresh(obj):
            if getattr(obj, "is_active", None) is None:
                obj.is_active = True
        mock_db.refresh.side_effect = mock_refresh
        
        # We also need to mock current_tenant_id and current_user_id
        # Wait, the endpoint uses Depends(get_current_user_dual) which returns user_id
        
        key_in = ApiKeyCreate(name="TestKey", scopes=["read", "write"], expires_at=None)
        
        with patch("app.api.v1.api_keys.current_tenant_id") as mock_tid:
            mock_tid.get.return_value = 1
            response = await create_api_key(key_in=key_in, db=mock_db, user_id=1)
            
        assert response["name"] == "TestKey"
        assert "raw_key" in response
        assert "key_prefix" in response
        assert response["is_active"] is True
        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    @patch("app.api.v1.api_keys.get_db")
    async def test_revoke_api_key_endpoint(self, mock_get_db):
        from app.api.v1.api_keys import revoke_api_key
        mock_db = AsyncMock()
        mock_result = MagicMock()
        
        valid_key = ApiKey(id=uuid.uuid4(), tenant_id=1, key_prefix="prefix", is_active=True)
        mock_result.scalars().first.return_value = valid_key
        mock_db.execute.return_value = mock_result
        
        with patch("app.api.v1.api_keys.current_tenant_id") as mock_tid:
            mock_tid.get.return_value = 1
            response = await revoke_api_key(key_id=valid_key.id, db=mock_db, user_id=1)
            
        assert response["is_active"] is False
        assert response["revoked_at"] is not None
        assert mock_db.commit.called
        
    @pytest.mark.asyncio
    @patch("app.api.v1.api_keys.get_db")
    async def test_rotate_api_key_endpoint(self, mock_get_db):
        from app.api.v1.api_keys import rotate_api_key
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        async def mock_refresh(obj):
            if getattr(obj, "is_active", None) is None:
                obj.is_active = True
        mock_db.refresh.side_effect = mock_refresh
        mock_result = MagicMock()
        
        valid_key = ApiKey(id=uuid.uuid4(), tenant_id=1, key_prefix="prefix", name="Key 1", scopes=[], is_active=True)
        mock_result.scalars().first.return_value = valid_key
        mock_db.execute.return_value = mock_result
        
        with patch("app.api.v1.api_keys.current_tenant_id") as mock_tid:
            mock_tid.get.return_value = 1
            response = await rotate_api_key(key_id=valid_key.id, db=mock_db, user_id=1)
            
        assert response["is_active"] is True
        assert valid_key.is_active is False
        assert mock_db.commit.called

class TestDualAuthMiddleware:
    @pytest.mark.asyncio
    @patch("app.api.middleware.auth_middleware.AsyncSessionLocal")
    async def test_auth_middleware_api_key(self, mock_session_local):
        # Setup mock db
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        # Valid active key
        valid_key = ApiKey(
            id=uuid.uuid4(),
            tenant_id=1,
            created_by=2,
            name="Test",
            key_prefix="prefix",
            key_hash="hash",
            is_active=True,
            expires_at=None,
            scopes=["read:alerts"]
        )
        mock_result.scalars().first.return_value = valid_key
        mock_session.execute.return_value = mock_result
        mock_session_local.return_value.__aenter__.return_value = mock_session

        # Setup mock request
        app = MagicMock()
        middleware = DualAuthMiddleware(app)
        request = Request(scope={
            "type": "http",
            "headers": [(b"x-api-key", b"test_raw_key")]
        })

        async def call_next(req):
            assert current_tenant_id.get() == 1
            assert current_user_id.get() == 2
            assert current_api_key.get() == "prefix"
            assert req.state.api_key_scopes == ["read:alerts"]
            return JSONResponse(status_code=200, content={"status": "ok"})

        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("app.api.middleware.auth_middleware.AsyncSessionLocal")
    async def test_auth_middleware_inactive_key(self, mock_session_local):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        inactive_key = ApiKey(
            id=uuid.uuid4(),
            tenant_id=1,
            created_by=2,
            is_active=False
        )
        mock_result.scalars().first.return_value = inactive_key
        mock_session.execute.return_value = mock_result
        mock_session_local.return_value.__aenter__.return_value = mock_session

        app = MagicMock()
        middleware = DualAuthMiddleware(app)
        request = Request(scope={
            "type": "http",
            "headers": [(b"x-api-key", b"test_raw_key")]
        })

        async def call_next(req):
            assert current_tenant_id.get() is None
            assert current_user_id.get() is None
            return JSONResponse(status_code=401, content={"status": "unauthorized"})

        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 401

    @pytest.mark.asyncio
    @patch("app.api.middleware.auth_middleware.AsyncSessionLocal")
    async def test_auth_middleware_expired_key(self, mock_session_local):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        expired_key = ApiKey(
            id=uuid.uuid4(),
            tenant_id=1,
            created_by=2,
            is_active=True,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        mock_result.scalars().first.return_value = expired_key
        mock_session.execute.return_value = mock_result
        mock_session_local.return_value.__aenter__.return_value = mock_session

        app = MagicMock()
        middleware = DualAuthMiddleware(app)
        request = Request(scope={
            "type": "http",
            "headers": [(b"x-api-key", b"test_raw_key")]
        })

        async def call_next(req):
            assert current_tenant_id.get() is None
            return JSONResponse(status_code=401, content={"status": "unauthorized"})

        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 401
