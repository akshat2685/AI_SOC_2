from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.infrastructure.database import get_db
from app.domain.models import User, Tenant, RoleEnum
from app.core.security import verify_password, get_password_hash, create_access_token

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == request.username))
    user = result.scalars().first()
    if not user or not verify_password(request.password, user.hashed_password):
        # The old server.js returned 401 with { detail: ... }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    access_token = create_access_token(
        subject=user.id, role=user.role, tenant_id=user.tenant_id
    )
    
    # Check if the user's tenant has premium status (placeholder for premium)
    premium = True  # TODO: get from tenant or user model
    
    return {
        "username": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "token": access_token,
        "premium": premium
    }

@router.post("/register")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Create default tenant if it doesn't exist
    tenant_result = await db.execute(select(Tenant).where(Tenant.name == "default"))
    tenant = tenant_result.scalars().first()
    if not tenant:
        tenant = Tenant(name="default")
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

    # Check if user exists
    user_result = await db.execute(select(User).where(User.email == request.username))
    if user_result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        email=request.username,
        hashed_password=get_password_hash(request.password),
        role=RoleEnum.TENANT_ADMIN,
        tenant_id=tenant.id
    )
    db.add(new_user)
    await db.commit()

    return {"status": "success", "username": request.username}
