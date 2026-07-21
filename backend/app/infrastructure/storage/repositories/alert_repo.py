from typing import Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models import Alert
from app.domain.schemas import AlertCreate
from app.infrastructure.storage.repositories.base import BaseRepository

class AlertRepository(BaseRepository[Alert, AlertCreate, Any]):
    def __init__(self, session: AsyncSession):
        super().__init__(Alert, session)

    async def get_by_incident(self, incident_id: int, tenant_id: Optional[int] = None) -> List[Alert]:
        await self._set_rls(tenant_id)
        stmt = select(Alert).where(Alert.incident_id == incident_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
