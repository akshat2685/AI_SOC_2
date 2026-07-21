from typing import Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models import AuditEvent
from app.domain.schemas import AuditEventCreate, AuditEventUpdate
from app.infrastructure.storage.repositories.base import BaseRepository

class AuditLogRepository(BaseRepository[AuditEvent, AuditEventCreate, AuditEventUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(AuditEvent, session)

    async def get_by_trace_id(self, trace_id: str, tenant_id: Optional[int] = None) -> List[AuditEvent]:
        await self._set_rls(tenant_id)
        stmt = select(AuditEvent).where(AuditEvent.trace_id == trace_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user(self, user_id: int, tenant_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[AuditEvent]:
        await self._set_rls(tenant_id)
        stmt = select(AuditEvent).where(AuditEvent.user_id == user_id).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def log_event(
        self,
        action: str,
        tenant_id: int,
        integrity_hash: str,
        user_id: Optional[int] = None,
        trace_id: Optional[str] = None,
        details: Optional[dict] = None
    ) -> AuditEvent:
        obj_in = AuditEventCreate(
            action=action,
            tenant_id=tenant_id,
            user_id=user_id,
            trace_id=trace_id,
            details=details or {},
            integrity_hash=integrity_hash
        )
        return await self.create(obj_in, tenant_id=tenant_id)
