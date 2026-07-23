from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.infrastructure.database import get_db
from app.domain.models import User, Tenant, RoleEnum
from app.core.security import verify_password, get_password_hash, create_access_token
from app.api.middleware.rate_limit_middleware import limiter

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, req_body: LoginRequest, db: AsyncSession = Depends(get_db)):
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
async def register(request: Request, req_body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    tenant_result = await db.execute(select(Tenant).where(Tenant.name == "default"))
    tenant = tenant_result.scalars().first()
    if not tenant:
        tenant = Tenant(name="default")
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

    user_result = await db.execute(select(User).where(User.email == req_body.username))
    if user_result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        email=req_body.username,
        hashed_password=get_password_hash(req_body.password),
        role=RoleEnum.TENANT_ADMIN,
        tenant_id=tenant.id
    )
    db.add(new_user)
    await db.commit()

    return {"status": "success", "username": req_body.username}
