from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jose import jwt, JWTError
from pydantic import ValidationError, BaseModel
from typing import Optional

from app.core.config import settings
from app.domain.models import RoleEnum
from app.core.auth import current_user_id, current_tenant_id

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

class TokenData(BaseModel):
    user_id: int
    role: RoleEnum
    tenant_id: Optional[int] = None

async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=["HS256"]
        )
        user_id = payload.get("sub")
        role = payload.get("role")
        tenant_id = payload.get("tenant_id")
        
        if user_id is None or role is None:
            raise HTTPException(status_code=403, detail="Could not validate credentials")
            
        token_data = TokenData(user_id=int(user_id), role=RoleEnum(role), tenant_id=tenant_id)
        return token_data
    except (JWTError, ValidationError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

async def check_api_key_scopes(security_scopes: SecurityScopes, request: Request):
    if security_scopes.scopes:
        api_key_scopes = getattr(request.state, "api_key_scopes", None)
        if api_key_scopes is not None:
            for scope in security_scopes.scopes:
                if scope not in api_key_scopes:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not enough permissions",
                    )
    return current_user_id.get()

async def get_current_user_dual(security_scopes: SecurityScopes, request: Request):
    """
    Dependency that enforces dual auth. It checks if the middleware already authenticated the user.
    If API Key was used, it enforces scopes.
    """
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    
    await check_api_key_scopes(security_scopes, request)
    return user_id

def require_roles(roles: list[RoleEnum]):
    def role_checker(current_user: TokenData = Depends(get_current_user)):
        if current_user.role not in roles and current_user.role != RoleEnum.GLOBAL_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker
