from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models import NotificationPreference, WebhookEndpoint, NotificationHistory
from app.domain.schemas import (
    NotificationPreferenceCreate, NotificationPreferenceUpdate,
    WebhookEndpointCreate, WebhookEndpointUpdate,
    NotificationHistoryBase
)
from app.infrastructure.storage.repositories.base import BaseRepository

class NotificationPreferenceRepository(BaseRepository[NotificationPreference, NotificationPreferenceCreate, NotificationPreferenceUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(NotificationPreference, session)

    async def get_by_tenant(self, tenant_id: int) -> List[NotificationPreference]:
        await self._set_rls(tenant_id)
        stmt = select(NotificationPreference).where(NotificationPreference.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

class WebhookEndpointRepository(BaseRepository[WebhookEndpoint, WebhookEndpointCreate, WebhookEndpointUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(WebhookEndpoint, session)

    async def get_active_by_tenant(self, tenant_id: int) -> List[WebhookEndpoint]:
        await self._set_rls(tenant_id)
        stmt = select(WebhookEndpoint).where(
            WebhookEndpoint.tenant_id == tenant_id,
            WebhookEndpoint.is_active == True
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

class NotificationHistoryRepository(BaseRepository[NotificationHistory, NotificationHistoryBase, NotificationHistoryBase]):
    def __init__(self, session: AsyncSession):
        super().__init__(NotificationHistory, session)

    async def get_recent_by_tenant(self, tenant_id: int, limit: int = 50) -> List[NotificationHistory]:
        await self._set_rls(tenant_id)
        stmt = (
            select(NotificationHistory)
            .where(NotificationHistory.tenant_id == tenant_id)
            .order_by(NotificationHistory.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
