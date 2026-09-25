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
    Propagates the tenant_id as a Postgres session variable for RLS policies.
    NOTE: SET LOCAL requires a transaction block, so this uses session-level
    SET and RESETs it before the connection returns to the pool (otherwise the
    tenant value would leak to the next borrower of the pooled connection).
    """
    async with AsyncSessionLocal() as session:
        tenant_id = current_tenant_id.get()
        is_pg = bool(session.bind and session.bind.dialect.name == "postgresql")
        try:
            if tenant_id is not None and is_pg:
                await session.execute(
                    text("SET rls.tenant_id = :tid"), {"tid": str(tenant_id)}
                )
            yield session
        finally:
            if tenant_id is not None and is_pg:
                try:
                    await session.execute(text("RESET rls.tenant_id"))
                except Exception:
                    pass
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
            is_pg = bool(session.bind and session.bind.dialect.name == "postgresql")
            if tenant_id is not None and is_pg:
                # SET LOCAL needs a transaction block; use session-level SET
                # and RESET it before returning the connection to the pool.
                await session.execute(
                    text("SET rls.tenant_id = :tid"), {"tid": str(tenant_id)}
                )
            try:
                yield session
            finally:
                if tenant_id is not None and is_pg:
                    try:
                        await session.execute(text("RESET rls.tenant_id"))
                    except Exception:
                        pass
    finally:
        if token is not None:
            current_tenant_id.reset(token)
