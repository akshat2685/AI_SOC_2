from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models import IntelligenceMetric
from app.domain.schemas import IntelligenceMetricCreate, IntelligenceMetricUpdate
from app.infrastructure.storage.repositories.base import BaseRepository

class IntelligenceMetricRepository(BaseRepository[IntelligenceMetric, IntelligenceMetricCreate, IntelligenceMetricUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(IntelligenceMetric, session)

    async def record_metric(
        self,
        metric_name: str,
        metric_value: float,
        tenant_id: int,
        dimensions: Optional[dict] = None
    ) -> IntelligenceMetric:
        obj_in = IntelligenceMetricCreate(
            metric_name=metric_name,
            metric_value=metric_value,
            tenant_id=tenant_id,
            dimensions=dimensions or {}
        )
        return await self.create(obj_in, tenant_id=tenant_id)

    async def get_by_metric_name(
        self,
        metric_name: str,
        tenant_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[IntelligenceMetric]:
        await self._set_rls(tenant_id)
        stmt = (
            select(IntelligenceMetric)
            .where(IntelligenceMetric.metric_name == metric_name)
            .order_by(IntelligenceMetric.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
