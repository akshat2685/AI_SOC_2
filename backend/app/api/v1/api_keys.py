from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import uuid

from app.infrastructure.database import get_db
from app.domain.models import ApiKey
from app.domain.schemas import ApiKeyCreate, ApiKeyResponse, ApiKeyCreateResponse
from app.infrastructure.security import generate_api_key
from app.api.deps import get_current_user_dual
from app.core.auth import current_tenant_id, current_user_id, current_trace_id
from app.core.logger import logger
from app.application.audit_logger import audit_logger

router = APIRouter()

@router.post("/", response_model=ApiKeyCreateResponse)
async def create_api_key(
    key_in: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_dual)
) -> Any:
    tenant_id = current_tenant_id.get()
    
    raw_key, key_prefix, key_hash = generate_api_key()
    
    db_obj = ApiKey(
        tenant_id=tenant_id,
        created_by=user_id,
        name=key_in.name,
        scopes=key_in.scopes,
        expires_at=key_in.expires_at,
        key_prefix=key_prefix,
        key_hash=key_hash
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    
    audit_logger.emit(
        action="api_key_created",
        tenant_id=tenant_id,
        user_id=user_id,
        trace_id=current_trace_id.get(),
        details={"key_prefix": key_prefix}
    )
    
    return {
        "id": str(db_obj.id),
        "name": db_obj.name,
        "scopes": db_obj.scopes,
        "expires_at": db_obj.expires_at,
        "is_active": db_obj.is_active,
        "created_at": db_obj.created_at,
        "last_used_at": db_obj.last_used_at,
        "revoked_at": db_obj.revoked_at,
        "key_prefix": db_obj.key_prefix,
        "raw_key": raw_key
    }

@router.get("/", response_model=List[ApiKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_dual)
) -> Any:
    tenant_id = current_tenant_id.get()
    result = await db.execute(select(ApiKey).where(ApiKey.tenant_id == tenant_id))
    return [{"id": str(k.id), **k.__dict__} for k in result.scalars().all()]

@router.get("/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_dual)
) -> Any:
    tenant_id = current_tenant_id.get()
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id))
    db_obj = result.scalars().first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="API Key not found")
    return {"id": str(db_obj.id), **db_obj.__dict__}

@router.post("/{key_id}/revoke", response_model=ApiKeyResponse)
async def revoke_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_dual)
) -> Any:
    tenant_id = current_tenant_id.get()
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id))
    db_obj = result.scalars().first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="API Key not found")
        
    db_obj.is_active = False
    db_obj.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(db_obj)
    
    audit_logger.emit(
        action="api_key_revoked",
        tenant_id=tenant_id,
        user_id=user_id,
        trace_id=current_trace_id.get(),
        details={"key_prefix": db_obj.key_prefix}
    )
    return {"id": str(db_obj.id), **db_obj.__dict__}

@router.post("/{key_id}/rotate", response_model=ApiKeyCreateResponse)
async def rotate_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_dual)
) -> Any:
    tenant_id = current_tenant_id.get()
    
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id))
    old_key = result.scalars().first()
    if not old_key:
        raise HTTPException(status_code=404, detail="API Key not found")
        
    old_key.is_active = False
    old_key.revoked_at = datetime.now(timezone.utc)
    
    raw_key, key_prefix, key_hash = generate_api_key()
    new_key = ApiKey(
        tenant_id=tenant_id,
        created_by=user_id,
        name=old_key.name,
        scopes=old_key.scopes,
        expires_at=old_key.expires_at,
        key_prefix=key_prefix,
        key_hash=key_hash
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    
    audit_logger.emit(
        action="api_key_rotated",
        tenant_id=tenant_id,
        user_id=user_id,
        trace_id=current_trace_id.get(),
        details={"old_key_prefix": old_key.key_prefix, "new_key_prefix": key_prefix}
    )
    
    return {
        "id": str(new_key.id),
        "name": new_key.name,
        "scopes": new_key.scopes,
        "expires_at": new_key.expires_at,
        "is_active": new_key.is_active,
        "created_at": new_key.created_at,
        "last_used_at": new_key.last_used_at,
        "revoked_at": new_key.revoked_at,
        "key_prefix": new_key.key_prefix,
        "raw_key": raw_key
    }
