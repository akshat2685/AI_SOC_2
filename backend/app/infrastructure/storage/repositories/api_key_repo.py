from typing import Optional, List
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models import ApiKey
from app.domain.schemas import ApiKeyCreate, ApiKeyUpdate
from app.infrastructure.storage.repositories.base import BaseRepository

class ApiKeyRepository(BaseRepository[ApiKey, ApiKeyCreate, ApiKeyUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(ApiKey, session)

    async def get_by_key_hash(self, key_hash: str) -> Optional[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_prefix(self, key_prefix: str) -> Optional[ApiKey]:
        stmt = select(ApiKey).where(ApiKey.key_prefix == key_prefix)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_for_tenant(self, tenant_id: int) -> List[ApiKey]:
        await self._set_rls(tenant_id)
        stmt = select(ApiKey).where(ApiKey.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
