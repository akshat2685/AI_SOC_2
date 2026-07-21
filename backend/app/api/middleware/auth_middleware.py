import hashlib
from datetime import datetime, timezone
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
from sqlalchemy import select, text
from app.core.config import settings
from app.infrastructure.database import AsyncSessionLocal
from app.domain.models import ApiKey
from app.core.auth import current_tenant_id, current_user_id, current_api_key
from app.core.logger import logger
from app.application.audit_logger import audit_logger

class DualAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization")
        api_key_header = request.headers.get("X-API-Key")
        
        tenant_id = None
        user_id = None
        api_key_prefix = None

        # 1. JWT Priority
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_sub = payload.get("sub")
                if user_sub:
                    user_id = int(user_sub)
                tenant_id = payload.get("tenant_id")
            except (JWTError, ValueError):
                pass
                
        # 2. Fallback to API Key
        is_api_key_auth = False
        if not user_id and api_key_header:
            key_hash = hashlib.sha256(api_key_header.encode()).hexdigest()
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
                api_key = result.scalars().first()
                
                if api_key and api_key.is_active and (not api_key.expires_at or api_key.expires_at > datetime.now(timezone.utc)):
                    tenant_id = api_key.tenant_id
                    user_id = api_key.created_by
                    api_key_prefix = api_key.key_prefix
                    is_api_key_auth = True
                    request.state.api_key_scopes = api_key.scopes
                    
                    # Log audit event (debounced in real implementation)
                    trace_id = request.state.trace_id if hasattr(request.state, 'trace_id') else getattr(request.state, 'trace_id', None)
                    audit_logger.emit(
                        action="api_key_usage",
                        tenant_id=tenant_id,
                        user_id=user_id,
                        trace_id=trace_id,
                        details={"key_prefix": api_key_prefix}
                    )
                    
                    # Redis Rate Limiter integration point
                    # e.g., await redis_client.incr(f"rate_limit:{api_key_prefix}")

        # 3. Set Context Vars
        token_tid = current_tenant_id.set(tenant_id)
        token_uid = current_user_id.set(user_id)
        token_ak = current_api_key.set(api_key_prefix)

        try:
            response = await call_next(request)
        finally:
            current_tenant_id.reset(token_tid)
            current_user_id.reset(token_uid)
            current_api_key.reset(token_ak)
            
        return response
