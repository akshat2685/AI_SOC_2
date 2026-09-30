from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import re
import uuid

from app.infrastructure.database import get_service_db
from app.domain.models import User, Tenant, RoleEnum
from app.core.security import verify_password, get_password_hash, create_access_token
from app.api.middleware.rate_limit_middleware import limiter

router = APIRouter()

# The login identity is stored in User.email — registration requires a real
# email shape so the "Email" label on the login form is honest.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, req_body: LoginRequest, db: AsyncSession = Depends(get_service_db)):
    result = await db.execute(select(User).where(User.email == req_body.username))
    user = result.scalars().first()
    if not user or not verify_password(req_body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    access_token = create_access_token(
        subject=user.id, role=user.role, tenant_id=user.tenant_id
    )
    
    premium = True
    
    return {
        "username": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "token": access_token,
        "premium": premium
    }

@router.post("/register")
@limiter.limit("3/minute")
async def register(request: Request, req_body: RegisterRequest, db: AsyncSession = Depends(get_service_db)):
    if not EMAIL_RE.match((req_body.username or "").strip()):
        raise HTTPException(status_code=400, detail="Please provide a valid email address")

    user_result = await db.execute(select(User).where(User.email == req_body.username))
    if user_result.scalars().first():
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    # Pentest CRITICAL-1: never attach self-registrations to the shared
    # "default" tenant. Every signup mints its OWN tenant (response_mode
    # defaults to dry_run) and is TENANT_ADMIN of that tenant only.
    tenant = Tenant(name=f"tenant-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()

    new_user = User(
        email=req_body.username,
        hashed_password=get_password_hash(req_body.password),
        role=RoleEnum.TENANT_ADMIN,
        tenant_id=tenant.id
    )
    db.add(new_user)
    await db.commit()

    return {"status": "success", "username": req_body.username, "tenant_id": tenant.id}
