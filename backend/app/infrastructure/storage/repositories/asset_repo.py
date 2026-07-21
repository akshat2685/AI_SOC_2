from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models import Asset
from app.domain.schemas import AssetCreate, AssetUpdate
from app.infrastructure.storage.repositories.base import BaseRepository

class AssetRepository(BaseRepository[Asset, AssetCreate, AssetUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(Asset, session)

    async def get_by_hostname(self, hostname: str, tenant_id: Optional[int] = None) -> Optional[Asset]:
        await self._set_rls(tenant_id)
        stmt = select(Asset).where(Asset.hostname == hostname)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_type(self, asset_type: str, tenant_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[Asset]:
        await self._set_rls(tenant_id)
        stmt = select(Asset).where(Asset.asset_type == asset_type).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
