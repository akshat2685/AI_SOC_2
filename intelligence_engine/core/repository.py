import logging
from typing import Type, TypeVar, Generic, Optional, Any, List, Dict
from sqlalchemy import create_engine, Column, String, Index
from sqlalchemy.orm import declarative_base, sessionmaker, Session, declared_attr
from sqlalchemy.sql import Select, Delete, Update
try:
    from core.config import get_settings
except ImportError:
    from intelligence_engine.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_engine(settings.db.postgres_url.replace("postgresql://", "postgresql+psycopg2://") if settings.db.postgres_url else "sqlite:///./soc.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class TenantBase(Base):
    __abstract__ = True
    
    tenant_id = Column(String(50), nullable=False, default="default")
    organization_id = Column(String(50), nullable=False, default="default")
    
    @declared_attr
    def __table_args__(cls):
        return (
            Index(f'ix_tenant_org_{cls.__tablename__}', 'tenant_id', 'organization_id'),
        )

T = TypeVar('T', bound=TenantBase)

class TenantQueryBuilder(Generic[T]):
    def __init__(self, model: Type[T], tenant_id: str, organization_id: str = None):
        self.model = model
        self.tenant_id = tenant_id
        self.organization_id = organization_id

    def filter(self, query: Any) -> Any:
        q = query.filter(self.model.tenant_id == self.tenant_id)
        if self.organization_id:
            q = q.filter(self.model.organization_id == self.organization_id)
        return q

class BaseRepository(Generic[T]):
    def __init__(self, session: Session, model: Type[T], tenant_id: str, organization_id: str = None):
        if not tenant_id:
            raise ValueError("tenant_id is required for strict ownership validation (RLS).")
        self.session = session
        self.model = model
        self.tenant_id = tenant_id
        self.organization_id = organization_id
        self.query_builder = TenantQueryBuilder(model, tenant_id, organization_id)
    
    def get_query(self):
        return self.query_builder.filter(self.session.query(self.model))
        
    def get(self, id: Any) -> Optional[T]:
        return self.get_query().filter(self.model.id == id).first()
        
    def get_all(self) -> List[T]:
        return self.get_query().all()
        
    def create(self, obj_in: Dict[str, Any]) -> T:
        # Enforce tenant_id and organization_id on creation
        obj_in['tenant_id'] = self.tenant_id
        if self.organization_id:
            obj_in['organization_id'] = self.organization_id
            
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def update(self, id: Any, obj_in: Dict[str, Any]) -> Optional[T]:
        db_obj = self.get(id)
        if not db_obj:
            return None
        
        # reject cross-tenant manipulation
        if db_obj.tenant_id != self.tenant_id:
            raise PermissionError("Cross-tenant access rejected")
            
        for field, value in obj_in.items():
            if field in ['tenant_id', 'organization_id']:
                continue
            setattr(db_obj, field, value)
            
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def delete(self, id: Any) -> bool:
        db_obj = self.get(id)
        if not db_obj:
            return False
            
        # reject cross-tenant manipulation
        if db_obj.tenant_id != self.tenant_id:
            raise PermissionError("Cross-tenant access rejected")
            
        self.session.delete(db_obj)
        self.session.commit()
        return True

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

try:
    from fastapi import Request, Depends
    def get_repository(model: Type[TenantBase]):
        def _get_repo(request: Request, db: Session = Depends(get_db)):
            tenant_id = getattr(request.state, "tenant_id", "default")
            organization_id = getattr(request.state, "organization_id", None)
            return BaseRepository(db, model, tenant_id, organization_id)
        return _get_repo
except ImportError:
    pass
