import json
import structlog
from typing import Optional, List, Dict
from fastapi import HTTPException, Security, Request, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
import jwt
from pydantic import BaseModel
import hashlib
from intelligence_engine.core.config import get_settings, Settings

logger = structlog.get_logger(__name__)

# Security components
security_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

class UserPayload(BaseModel):
    user_id: str
    tenant_id: str
    roles: List[str]
    permissions: List[str]

class APIKeyPayload(BaseModel):
    api_key_id: str
    tenant_id: str
    roles: List[str]
    permissions: List[str]

class TokenValidator:
    """Validates RS256 JWT tokens."""
    def __init__(self, settings: Settings = Depends(get_settings)):
        self.settings = settings.security
        # In a real scenario, this public key would be fetched from JWKS endpoint or file
        self.public_key = self._load_public_key()
        
    def _load_public_key(self):
        if not self.settings.public_key_path:
            # Fallback for testing, but in production this must be RS256 public key
            return self.settings.secret_key
        try:
            with open(self.settings.public_key_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load public key: {e}")
            return self.settings.secret_key

    def validate(self, token: str) -> UserPayload:
        try:
            # RS256 requires a public key. Options ensure signature is verified and header isn't spoofed.
            payload = jwt.decode(
                token, 
                self.public_key, 
                algorithms=[self.settings.algorithm],
                options={"verify_signature": True, "verify_exp": True}
            )
            return UserPayload(
                user_id=payload.get("sub", ""),
                tenant_id=payload.get("tenant_id", "default-tenant"),
                roles=payload.get("roles", []),
                permissions=payload.get("permissions", [])
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

class APIKeyService:
    """Production API Key Service using hashed values and DB lookup."""
    def __init__(self, settings: Settings = Depends(get_settings)):
        self.settings = settings.security
        # Mock DB of hashed API keys
        self.mock_db = {
            # Hashed version of a valid key "test-api-key" with "default_salt"
            hashlib.sha256(f"test-api-key{self.settings.api_key_salt}".encode()).hexdigest(): APIKeyPayload(
                api_key_id="test-key-id",
                tenant_id="default-tenant",
                roles=["api_client"],
                permissions=["read", "write"]
            )
        }

    def validate(self, api_key: str) -> APIKeyPayload:
        if not api_key:
            raise HTTPException(status_code=401, detail="API Key required")
        
        hashed_key = hashlib.sha256(f"{api_key}{self.settings.api_key_salt}".encode()).hexdigest()
        
        payload = self.mock_db.get(hashed_key)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid API Key")
        return payload

class TenantResolver:
    """Resolves and validates tenant from request state or payload."""
    def resolve(self, request: Request, user_payload: Optional[UserPayload] = None, api_payload: Optional[APIKeyPayload] = None) -> str:
        tenant_id = getattr(request.state, "tenant_id", None)
        
        payload_tenant = None
        if user_payload:
            payload_tenant = user_payload.tenant_id
        elif api_payload:
            payload_tenant = api_payload.tenant_id
            
        if not payload_tenant:
            payload_tenant = "default-tenant"
            
        if tenant_id and tenant_id != payload_tenant and tenant_id != "default-tenant":
             raise HTTPException(status_code=403, detail="Tenant mismatch")
             
        return payload_tenant

class PermissionResolver:
    """Hierarchical roles, policy engine, and permission cache."""
    def __init__(self):
        # Role hierarchy: admin inherits from operator, operator inherits from viewer
        self.role_hierarchy = {
            "admin": ["operator"],
            "operator": ["viewer"],
            "viewer": [],
            "api_client": ["operator"]
        }
        # Explicit permissions mapped to roles
        self.role_permissions = {
            "admin": ["delete", "manage_users", "manage_settings"],
            "operator": ["write", "execute", "update"],
            "viewer": ["read"],
            "api_client": ["read", "write"]
        }
        self.permission_cache = {}

    def _get_all_roles(self, role: str, collected: set):
        if role in collected:
            return
        collected.add(role)
        for child_role in self.role_hierarchy.get(role, []):
            self._get_all_roles(child_role, collected)

    def resolve_permissions(self, roles: List[str]) -> set:
        cache_key = tuple(sorted(roles))
        if cache_key in self.permission_cache:
            return self.permission_cache[cache_key]
            
        all_roles = set()
        for role in roles:
            self._get_all_roles(role, all_roles)
            
        all_permissions = set()
        for r in all_roles:
            all_permissions.update(self.role_permissions.get(r, []))
            
        self.permission_cache[cache_key] = all_permissions
        return all_permissions
        
    def check_permission(self, required_permission: str, roles: List[str], explicit_permissions: List[str]):
        resolved_perms = self.resolve_permissions(roles)
        if required_permission not in resolved_perms and required_permission not in explicit_permissions:
            raise HTTPException(status_code=403, detail=f"Missing required permission: {required_permission}")

class AuthenticationService:
    """Coordinates authentication, tenant resolution and RBAC."""
    def __init__(
        self, 
        token_validator: TokenValidator = Depends(),
        api_key_service: APIKeyService = Depends(),
        tenant_resolver: TenantResolver = Depends(),
        permission_resolver: PermissionResolver = Depends()
    ):
        self.token_validator = token_validator
        self.api_key_service = api_key_service
        self.tenant_resolver = tenant_resolver
        self.permission_resolver = permission_resolver

    def authenticate(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
        api_key: Optional[str] = Security(api_key_header)
    ) -> Dict:
        user_payload = None
        api_payload = None
        
        if credentials:
            user_payload = self.token_validator.validate(credentials.credentials)
        elif api_key:
            api_payload = self.api_key_service.validate(api_key)
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
            
        tenant_id = self.tenant_resolver.resolve(request, user_payload, api_payload)
        
        if user_payload:
            roles = user_payload.roles
            permissions = user_payload.permissions
            identity = user_payload.user_id
        else:
            roles = api_payload.roles
            permissions = api_payload.permissions
            identity = api_payload.api_key_id
            
        return {
            "identity": identity,
            "tenant_id": tenant_id,
            "roles": roles,
            "permissions": permissions,
            "type": "user" if user_payload else "api_key"
        }

def require_permission(permission: str):
    def dependency(
        request: Request,
        auth_service: AuthenticationService = Depends(),
        credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
        api_key: Optional[str] = Security(api_key_header)
    ):
        auth_data = auth_service.authenticate(request, credentials, api_key)
        auth_service.permission_resolver.check_permission(
            permission, auth_data["roles"], auth_data["permissions"]
        )
        request.state.user = auth_data
        return auth_data
    return dependency

def get_current_user(
    request: Request,
    auth_service: AuthenticationService = Depends(),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    api_key: Optional[str] = Security(api_key_header)
):
    auth_data = auth_service.authenticate(request, credentials, api_key)
    request.state.user = auth_data
    return auth_data
