from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager
from contextvars import ContextVar
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession
from app.core.auth import current_tenant_id, current_user_id
from app.infrastructure.storage.engine import AsyncSessionLocal

# RLS roles (see migration 0011_rls_enforcement):
#   'tenant'  -> session sees only rows for rls.tenant_id (default-deny otherwise)
#   'service' -> privileged paths only: login, register, API-key resolution,
#                seeding, background loops. Never for serving tenant data.
_ROLE_TENANT = "tenant"
_ROLE_SERVICE = "service"

# Which RLS role the current execution context wants on every DB transaction.
# Set by get_db / service_scope / tenant_scope; consumed by the after_begin
# listener below. The listener re-applies the GUCs per-transaction because a
# session-level SET does not survive `commit()`: commit returns the physical
# connection to the pool, and the next statement (e.g. `refresh()` after an
# insert) may run on a different pooled connection whose GUCs were reset —
# under RLS default-deny the just-committed row is then invisible and
# refresh() raises InvalidRequestError (the live POST /api-keys/ 500).
_current_db_role: ContextVar[Optional[str]] = ContextVar("rls_db_role", default=None)


@event.listens_for(SyncSession, "after_begin")
def _rls_after_begin(session, transaction, connection) -> None:
    """Re-apply the RLS GUCs (transaction-local) at every transaction begin.

    Fires for sync and async sessions alike (async sessions bridge to the
    sync Session). No-op on non-Postgres dialects (tests run sqlite) and
    when no role/tenant is in context (public routes stay default-deny).
    """
    if connection.dialect.name != "postgresql":
        return
    role = _current_db_role.get()
    tenant_id = current_tenant_id.get()
    if role is None and tenant_id is not None:
        role = _ROLE_TENANT
    if role is None:
        return
    connection.execute(
        text("SELECT set_config('rls.app_role', :role, true)"), {"role": role}
    )
    if tenant_id is not None:
        connection.execute(
            text("SELECT set_config('rls.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )


def set_tenant_context(tenant_id: Optional[int]) -> None:
    """Sets the global tenant ID ContextVar for the current execution context."""
    current_tenant_id.set(tenant_id)

def get_tenant_context() -> Optional[int]:
    """Retrieves the active tenant ID from ContextVars."""
    return current_tenant_id.get()


async def _apply_role(session: AsyncSession, role: str, tenant_id: Optional[int] = None) -> None:
    """Set the RLS GUCs on a session. Plain SET takes no bind params;
    set_config() is the parameter-safe equivalent."""
    await session.execute(
        text("SELECT set_config('rls.app_role', :role, false)"), {"role": role}
    )
    if tenant_id is not None:
        await session.execute(
            text("SELECT set_config('rls.tenant_id', :tid, false)"), {"tid": str(tenant_id)}
        )


async def _reset_role(session: AsyncSession) -> None:
    """RESET the RLS GUCs before the connection returns to the pool,
    otherwise the role would leak to the next borrower."""
    for guc in ("rls.app_role", "rls.tenant_id"):
        try:
            await session.execute(text(f"RESET {guc}"))
        except Exception:
            pass


def _is_pg(session: AsyncSession) -> bool:
    return bool(session.bind and session.bind.dialect.name == "postgresql")


async def _clean_session(session: AsyncSession, is_pg: bool) -> None:
    """Return a session to the pool with no RLS role attached.

    Rolls back any open transaction (discards nothing already committed),
    RESETs the RLS GUCs, and commits so the reset survives on the pooled
    connection. Without the commit, close() would roll the RESET back and
    leak the role to the next borrower.
    """
    if not is_pg:
        return
    try:
        await session.rollback()
    except Exception:
        pass
    await _reset_role(session)
    try:
        await session.commit()
    except Exception:
        pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    - Authenticated request (tenant in ContextVar) -> rls.app_role='tenant'
      + rls.tenant_id: the session sees ONLY that tenant's rows (DB-enforced).
    - No tenant (unauthenticated / public route) -> no GUCs are set, so RLS
      default-deny applies: tenant tables return zero rows. This is what
      closes the unauthenticated /audit-log hole at the database layer.
    """
    async with AsyncSessionLocal() as session:
        tenant_id = current_tenant_id.get()
        is_pg = _is_pg(session)
        role_token = None
        if tenant_id is not None:
            role_token = _current_db_role.set(_ROLE_TENANT)
        try:
            if tenant_id is not None and is_pg:
                await _apply_role(session, _ROLE_TENANT, tenant_id)
            yield session
        finally:
            # Roll back any stray transaction, RESET the RLS GUCs, and COMMIT
            # the reset. The commit is load-bearing: without it, close()
            # rolls the RESET back and the pooled connection leaks the role
            # to its next borrower (cross-tenant leak). A rollback also
            # clears session-level GUCs, so a session that rolled back runs
            # fail-closed (default-deny) afterwards — re-enter the scope to
            # continue working.
            await _clean_session(session, is_pg)
            await session.close()
            if role_token is not None:
                _current_db_role.reset(role_token)


async def get_service_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for privileged lookups that must run BEFORE a
    tenant is known: login, registration. Sets rls.app_role='service'."""
    async with service_scope() as session:
        yield session


@asynccontextmanager
async def service_scope() -> AsyncGenerator[AsyncSession, None]:
    """Privileged DB scope (rls.app_role='service').

    Use ONLY for: login, register, API-key resolution, DB seeding, and
    background loops that legitimately span tenants. NEVER in a request
    handler that serves tenant data — that would bypass tenant isolation.
    """
    async with AsyncSessionLocal() as session:
        is_pg = _is_pg(session)
        role_token = _current_db_role.set(_ROLE_SERVICE)
        try:
            if is_pg:
                await _apply_role(session, _ROLE_SERVICE)
            yield session
        finally:
            await _clean_session(session, is_pg)
            await session.close()
            _current_db_role.reset(role_token)


@asynccontextmanager
async def tenant_scope(tenant_id: Optional[int] = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for background workers and non-HTTP tasks requiring tenant RLS propagation.
    Sets rls.app_role='tenant' + rls.tenant_id so background work gets the
    same DB-level isolation as request handlers.
    """
    token = None
    role_token = None
    if tenant_id is not None:
        token = current_tenant_id.set(tenant_id)
        role_token = _current_db_role.set(_ROLE_TENANT)
    try:
        async with AsyncSessionLocal() as session:
            is_pg = _is_pg(session)
            if tenant_id is not None and is_pg:
                await _apply_role(session, _ROLE_TENANT, tenant_id)
            try:
                yield session
            finally:
                await _clean_session(session, is_pg)
    finally:
        if token is not None:
            current_tenant_id.reset(token)
        if role_token is not None:
            _current_db_role.reset(role_token)
