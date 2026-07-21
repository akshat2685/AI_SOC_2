from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.domain.models import Incident, SeverityEnum, StatusEnum
from app.domain.schemas import IncidentCreate, IncidentUpdate
from app.infrastructure.storage.repositories.base import BaseRepository

class IncidentRepository(BaseRepository[Incident, IncidentCreate, IncidentUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(Incident, session)

    async def get_with_alerts(self, id: int, tenant_id: Optional[int] = None) -> Optional[Incident]:
        await self._set_rls(tenant_id)
        stmt = select(Incident).options(selectinload(Incident.alerts)).where(Incident.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_severity(self, severity: SeverityEnum, tenant_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[Incident]:
        await self._set_rls(tenant_id)
        stmt = select(Incident).where(Incident.severity == severity).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(self, status: StatusEnum, tenant_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[Incident]:
        await self._set_rls(tenant_id)
        stmt = select(Incident).where(Incident.status == status).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
