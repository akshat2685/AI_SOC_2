import pytest
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncEngine

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.domain.models import Tenant, User, Incident, AuditEvent, IntelligenceMetric
from app.domain.schemas import (
    TenantCreate, UserCreate, IncidentCreate, AuditEventCreate, IntelligenceMetricCreate
)
from app.infrastructure.storage import (
    create_storage_engine,
    dispose_engine,
    AsyncSessionLocal,
    get_db,
    tenant_scope,
    set_tenant_context,
    get_tenant_context,
    BaseRepository,
    TenantRepository,
    UserRepository,
    IncidentRepository,
    AuditLogRepository,
    IntelligenceMetricRepository,
    AssetRepository,
    AlertRepository,
    ApiKeyRepository,
)
import app.infrastructure.database as db_facade
import app.infrastructure.repositories as repo_facade

class TestEngineAndSessionCreation:
    """Validates Async Database Engine and Session creation."""
    
    def test_create_sqlite_storage_engine(self):
        engine = create_storage_engine("sqlite+aiosqlite:///:memory:")
        assert isinstance(engine, AsyncEngine)
        assert engine.dialect.name == "sqlite"

    def test_create_postgres_storage_engine(self):
        engine = create_storage_engine("postgresql+asyncpg://user:pass@localhost:5432/db")
        assert isinstance(engine, AsyncEngine)
        assert engine.dialect.name == "postgresql"

    @pytest.mark.asyncio
    async def test_session_lifecycle_and_dispose(self):
        mock_engine = AsyncMock()
        with patch("app.infrastructure.storage.engine.engine", mock_engine):
            await dispose_engine()
            mock_engine.dispose.assert_called_once()

class TestMultiTenantRLSAndContext:
    """Validates multi-tenancy RLS isolation and session context handling."""

    def test_tenant_context_vars(self):
        set_tenant_context(101)
        assert get_tenant_context() == 101
        set_tenant_context(None)
        assert get_tenant_context() is None

    @pytest.mark.asyncio
    async def test_tenant_scope_context_manager(self):
        set_tenant_context(None)
        mock_session = AsyncMock()
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        mock_session.bind = mock_bind
        
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("app.infrastructure.storage.context.AsyncSessionLocal", return_value=mock_cm):
            async with tenant_scope(tenant_id=42) as session:
                assert get_tenant_context() == 42
                assert session == mock_session
                assert mock_session.execute.called
                exec_arg = str(mock_session.execute.call_args[0][0])
                assert "SET LOCAL rls.tenant_id = '42'" in exec_arg
            
            # Context must reset after exiting block
            assert get_tenant_context() is None

    @pytest.mark.asyncio
    async def test_get_db_fastapi_dependency_with_rls(self):
        set_tenant_context(99)
        mock_session = AsyncMock()
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        mock_session.bind = mock_bind
        
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("app.infrastructure.storage.context.AsyncSessionLocal", return_value=mock_cm):
            db_gen = get_db()
            session = await anext(db_gen)
            assert session == mock_session
            assert mock_session.execute.called
            exec_arg = str(mock_session.execute.call_args[0][0])
            assert "SET LOCAL rls.tenant_id = '99'" in exec_arg
            
            # Clean up generator
            try:
                await anext(db_gen)
            except StopAsyncIteration:
                pass
            
            mock_session.close.assert_called_once()
        set_tenant_context(None)

class TestRepositoryCRUDAndAsyncLoad:
    """Validates Repository CRUD operations and performance under async load."""

    @pytest.mark.asyncio
    async def test_user_repository_rls_propagation(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_user = User(id=1, tenant_id=10, email="user@tenant.com")
        mock_result.scalar_one_or_none.return_value = mock_user
        session.execute.return_value = mock_result

        repo = UserRepository(session)
        user = await repo.get(id=1, tenant_id=10)

        assert session.execute.call_count == 2
        rls_call = session.execute.call_args_list[0]
        assert "SET LOCAL rls.tenant_id" in str(rls_call[0][0])
        assert rls_call[0][1] == {"tenant_id": "10"}
        assert user.email == "user@tenant.com"

    @pytest.mark.asyncio
    async def test_audit_log_repository_create(self):
        session = AsyncMock()
        mock_result = MagicMock()
        session.execute.return_value = mock_result

        repo = AuditLogRepository(session)
        event = await repo.log_event(
            action="user_login",
            tenant_id=5,
            integrity_hash="abc123hash",
            user_id=42,
            details={"ip": "127.0.0.1"}
        )

        assert session.add.called
        assert session.commit.called

    @pytest.mark.asyncio
    async def test_intelligence_metric_repository_record(self):
        session = AsyncMock()
        mock_result = MagicMock()
        session.execute.return_value = mock_result

        repo = IntelligenceMetricRepository(session)
        metric = await repo.record_metric(
            metric_name="cpu_usage",
            metric_value=85.5,
            tenant_id=5,
            dimensions={"host": "server-1"}
        )

        assert session.add.called
        assert session.commit.called

    @pytest.mark.asyncio
    async def test_repository_crud_under_async_load(self):
        """Executes 100 concurrent async CRUD operations to simulate heavy load."""
        async def simulate_crud_op(tenant_id: int, user_id: int):
            session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = User(id=user_id, tenant_id=tenant_id, email=f"user{user_id}@t{tenant_id}.com")
            session.execute.return_value = mock_result
            
            repo = UserRepository(session)
            user = await repo.get(id=user_id, tenant_id=tenant_id)
            return user.tenant_id

        tasks = [simulate_crud_op(tenant_id=i % 10, user_id=i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 100
        assert results[0] == 0
        assert results[99] == 9

class TestBackwardCompatibility:
    """Validates backward compatibility facades delegating to native storage engine."""

    def test_database_facade_exports(self):
        assert hasattr(db_facade, "create_storage_engine") or hasattr(db_facade, "get_db")
        assert db_facade.get_db == get_db
        assert db_facade.tenant_scope == tenant_scope
        assert db_facade.AsyncSessionLocal == AsyncSessionLocal

    def test_repository_facade_exports(self):
        assert repo_facade.BaseRepository == BaseRepository
        assert repo_facade.UserRepository == UserRepository
        assert repo_facade.TenantRepository == TenantRepository
        assert repo_facade.IncidentRepository == IncidentRepository
        assert repo_facade.AuditLogRepository == AuditLogRepository


class TestStorageContextAndMultiModalClients:
    """Validates the new multi-modal StorageContext and engine enhancements."""

    def test_storage_context_instantiation(self):
        from app.infrastructure.storage.engine import StorageContext
        session_mock = MagicMock()
        neo4j_mock = MagicMock()
        qdrant_mock = MagicMock()
        
        ctx = StorageContext(session_mock, neo4j_mock, qdrant_mock)
        assert ctx.session == session_mock
        assert ctx.neo4j == neo4j_mock
        assert ctx.qdrant == qdrant_mock

    def test_base_repository_context_injection(self):
        from app.infrastructure.storage.engine import StorageContext
        from app.domain.models import User
        session_mock = MagicMock()
        
        with patch('app.infrastructure.storage.repositories.base.StorageContext', StorageContext):
            repo = BaseRepository(User, session_mock)
            assert repo.context is not None
            assert isinstance(repo.context, StorageContext)
            assert repo.context.session == session_mock

    @pytest.mark.asyncio
    async def test_dispose_engine_with_clients(self):
        from app.infrastructure.storage import engine
        
        mock_engine = AsyncMock()
        mock_neo4j = AsyncMock()
        mock_qdrant = AsyncMock()
        mock_qdrant.close = AsyncMock()
        
        with patch.object(engine, 'engine', mock_engine), \
             patch.object(engine, 'neo4j_driver', mock_neo4j), \
             patch.object(engine, 'qdrant_client', mock_qdrant):
             
             await engine.dispose_engine()
             
             mock_engine.dispose.assert_called_once()
             mock_neo4j.close.assert_called_once()
             mock_qdrant.close.assert_called_once()
