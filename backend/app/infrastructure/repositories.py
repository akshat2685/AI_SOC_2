from typing import List, Optional, TypeVar, Generic, Type, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.domain.models import Base, Incident, Alert
from app.domain.schemas import IncidentCreate, IncidentUpdate, AlertCreate

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")

class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get(self, id: Any) -> Optional[ModelType]:
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        obj_in_data = obj_in.model_dump()
        db_obj = self.model(**obj_in_data)
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def update(self, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def remove(self, id: Any) -> Optional[ModelType]:
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj:
            await self.session.delete(obj)
            await self.session.commit()
        return obj

class IncidentRepository(BaseRepository[Incident, IncidentCreate, IncidentUpdate]):
    def __init__(self, session: AsyncSession):
        super().__init__(Incident, session)

    async def get_with_alerts(self, id: int) -> Optional[Incident]:
        stmt = select(Incident).options(selectinload(Incident.alerts)).where(Incident.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

class AlertRepository(BaseRepository[Alert, AlertCreate, Any]):
    def __init__(self, session: AsyncSession):
        super().__init__(Alert, session)

    async def get_by_incident(self, incident_id: int) -> List[Alert]:
        stmt = select(Alert).where(Alert.incident_id == incident_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
