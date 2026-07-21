import json
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from cryptography.fernet import Fernet
import httpx

from app.infrastructure.database import get_db
from app.api.deps import require_roles, TokenData
from app.domain.models import RoleEnum, NotificationPreference, WebhookEndpoint, NotificationHistory
from app.domain.schemas import (
    NotificationPreferenceCreate, NotificationPreferenceUpdate, NotificationPreference as NotificationPreferenceSchema,
    WebhookEndpointCreate, WebhookEndpointUpdate, WebhookEndpoint as WebhookEndpointSchema,
    NotificationHistory as NotificationHistorySchema
)
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../intelligence_engine")))
from core.crypto import envelope_crypto


# PREFERENCES
@router.post("/preferences", response_model=NotificationPreferenceSchema)
async def create_preference(
    pref_in: NotificationPreferenceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(require_roles([RoleEnum.TENANT_ADMIN]))
):
    db_pref = NotificationPreference(**pref_in.model_dump(), tenant_id=current_user.tenant_id)
    db.add(db_pref)
    await db.commit()
    await db.refresh(db_pref)
    return db_pref

@router.get("/preferences", response_model=List[NotificationPreferenceSchema])
async def list_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(require_roles([RoleEnum.TENANT_ADMIN]))
):
    result = await db.execute(select(NotificationPreference).where(NotificationPreference.tenant_id == current_user.tenant_id))
    return result.scalars().all()

@router.put("/preferences/{id}", response_model=NotificationPreferenceSchema)
async def update_preference(
    id: int,
    pref_in: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(require_roles([RoleEnum.TENANT_ADMIN]))
):
    result = await db.execute(select(NotificationPreference).where(NotificationPreference.id == id, NotificationPreference.tenant_id == current_user.tenant_id))
    db_pref = result.scalars().first()
    if not db_pref:
        raise HTTPException(status_code=404, detail="Preference not found")
    
    update_data = pref_in.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(db_pref, k, v)
    
    await db.commit()
    await db.refresh(db_pref)
    return db_pref


# WEBHOOKS
@router.post("/webhooks", response_model=WebhookEndpointSchema)
async def create_webhook(
    wh_in: WebhookEndpointCreate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(require_roles([RoleEnum.TENANT_ADMIN]))
):
    if not wh_in.url.startswith("https://"):
        raise HTTPException(status_code=400, detail="URL must start with https://")
    
    encrypted_secret = await envelope_crypto.encrypt_async(current_user.tenant_id, wh_in.secret, db)
    dump = wh_in.model_dump()
    dump["secret"] = encrypted_secret
    
    db_wh = WebhookEndpoint(**dump, tenant_id=current_user.tenant_id)
    db.add(db_wh)
    await db.commit()
    await db.refresh(db_wh)
    return db_wh

@router.get("/webhooks", response_model=List[WebhookEndpointSchema])
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(require_roles([RoleEnum.TENANT_ADMIN]))
):
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == current_user.tenant_id))
    return result.scalars().all()

@router.post("/webhooks/{id}/test")
async def test_webhook(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(require_roles([RoleEnum.TENANT_ADMIN]))
):
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == id, WebhookEndpoint.tenant_id == current_user.tenant_id))
    db_wh = result.scalars().first()
    if not db_wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    payload = {"event": "test"}
    body_bytes = json.dumps(payload).encode('utf-8')
    try:
        secret = await envelope_crypto.decrypt_async(current_user.tenant_id, db_wh.secret, db)
    except Exception:
        secret = db_wh.secret.encode('utf-8')
    
    import hmac, hashlib
    signature = hmac.new(secret if isinstance(secret, (bytes, bytearray)) else secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()
    
    if isinstance(secret, bytearray):
        for i in range(len(secret)):
            secret[i] = 0
    elif isinstance(secret, bytes) and secret:
        import ctypes
        import sys
        try:
            offset = 32 if sys.maxsize > 2**32 else 16
            ctypes.memset(id(secret) + offset, 0, len(secret))
        except Exception:
            pass

    headers = {
        "Content-Type": "application/json",
        "X-Edysor-Signature": f"sha256={signature}"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(db_wh.url, content=body_bytes, headers=headers, timeout=5.0)
            return {"status": resp.status_code, "body": resp.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# HISTORY
@router.get("/history", response_model=List[NotificationHistorySchema])
async def list_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: TokenData = Depends(require_roles([RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]))
):
    result = await db.execute(
        select(NotificationHistory)
        .where(NotificationHistory.tenant_id == current_user.tenant_id)
        .order_by(NotificationHistory.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
