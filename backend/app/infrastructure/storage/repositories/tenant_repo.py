from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models import Tenant
from app.domain.schemas import TenantCreate, TenantUpdate
from app.infrastructure.storage.repositories.base import BaseRepository

class TenantRepository(BaseRepository[Tenant, TenantCreate, TenantUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(Tenant, session)

    async def get_by_name(self, name: str) -> Optional[Tenant]:
        stmt = select(Tenant).where(Tenant.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
