from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import current_tenant_id, current_user_id
from app.infrastructure.storage.engine import AsyncSessionLocal

def set_tenant_context(tenant_id: Optional[int]) -> None:
    """Sets the global tenant ID ContextVar for the current execution context."""
    current_tenant_id.set(tenant_id)

def get_tenant_context() -> Optional[int]:
    """Retrieves the active tenant ID from ContextVars."""
    return current_tenant_id.get()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    Automatically sets Postgres RLS tenant_id local variable if tenant_id context is active.
    """
    async with AsyncSessionLocal() as session:
        try:
            tenant_id = current_tenant_id.get()
            if tenant_id is not None:
                if session.bind and session.bind.dialect.name == "postgresql":
                    await session.execute(text(f"SET LOCAL rls.tenant_id = '{tenant_id}'"))
            yield session
        finally:
            await session.close()

@asynccontextmanager
async def tenant_scope(tenant_id: Optional[int] = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for background workers and non-HTTP tasks requiring tenant RLS propagation.
    """
    token = None
    if tenant_id is not None:
        token = current_tenant_id.set(tenant_id)
    try:
        async with AsyncSessionLocal() as session:
            if tenant_id is not None and session.bind and session.bind.dialect.name == "postgresql":
                await session.execute(text(f"SET LOCAL rls.tenant_id = '{tenant_id}'"))
            yield session
    finally:
        if token is not None:
            current_tenant_id.reset(token)
