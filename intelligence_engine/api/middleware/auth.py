from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from typing import Optional
from intelligence_engine.api.services.security import (
    AuthenticationService,
    TokenValidator,
    APIKeyService,
    TenantResolver,
    PermissionResolver,
    get_current_user as security_get_current_user,
    require_permission,
    security_scheme,
    api_key_header
)

# Export legacy functions as wrappers
async def verify_jwt(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)):
    if not credentials:
        return None
    validator = TokenValidator()
    return validator.validate(credentials.credentials)

async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    if not api_key:
        return None
    service = APIKeyService()
    return service.validate(api_key)

async def get_current_user(
    auth_data = Depends(security_get_current_user)
):
    return auth_data
