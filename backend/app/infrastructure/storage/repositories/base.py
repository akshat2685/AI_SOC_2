from typing import List, Optional, TypeVar, Generic, Type, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from app.domain.models import Base

try:
    from app.infrastructure.storage.engine import StorageContext, neo4j_driver, qdrant_client
except ImportError:
    StorageContext = None
    neo4j_driver = None
    qdrant_client = None

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")

class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    Generic Repository Pattern wrapper handling standard CRUD actions and automatic RLS enforcement.
    """
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session
        if StorageContext:
            self.context = StorageContext(session, neo4j_driver, qdrant_client)
        else:
            self.context = None

    async def _set_rls(self, tenant_id: Optional[int]):
        """Executes RLS session parameter setting if supported/requested."""
        if tenant_id is not None:
            await self.session.execute(text("SET LOCAL rls.tenant_id = :tenant_id"), {"tenant_id": str(tenant_id)})
        else:
            await self.session.execute(text("SET LOCAL rls.tenant_id = ''"))

    async def get(self, id: Any, tenant_id: Optional[int] = None) -> Optional[ModelType]:
        await self._set_rls(tenant_id)
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100, tenant_id: Optional[int] = None) -> List[ModelType]:
        await self._set_rls(tenant_id)
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, tenant_id: Optional[int] = None) -> int:
        await self._set_rls(tenant_id)
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def create(self, obj_in: CreateSchemaType, tenant_id: Optional[int] = None) -> ModelType:
        if isinstance(obj_in, dict):
            obj_in_data = obj_in.copy()
        elif hasattr(obj_in, "model_dump"):
            obj_in_data = obj_in.model_dump()
        else:
            obj_in_data = dict(obj_in)
        
        if hasattr(self.model, "tenant_id"):
            final_tenant_id = tenant_id or obj_in_data.get("tenant_id")
            if final_tenant_id is None:
                column = self.model.__table__.columns.get("tenant_id")
                if column is not None and not column.nullable:
                    raise ValueError("tenant_id is required to create tenant-specific records")
            if final_tenant_id is not None:
                obj_in_data["tenant_id"] = final_tenant_id

        await self._set_rls(tenant_id)
        db_obj = self.model(**obj_in_data)
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def update(self, db_obj: ModelType, obj_in: UpdateSchemaType, tenant_id: Optional[int] = None) -> ModelType:
        if isinstance(obj_in, dict):
            update_data = obj_in.copy()
        elif hasattr(obj_in, "model_dump"):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = dict(obj_in)

        # Explicitly remove tenant_id to prevent cross-tenant data leakage
        update_data.pop("tenant_id", None)
        
        await self._set_rls(tenant_id)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def remove(self, id: Any, tenant_id: Optional[int] = None) -> Optional[ModelType]:
        await self._set_rls(tenant_id)
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj:
            await self.session.delete(obj)
            await self.session.commit()
        return obj
