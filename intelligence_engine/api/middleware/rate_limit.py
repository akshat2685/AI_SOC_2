import time
import logging
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

try:
    import redis.asyncio as redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    
try:
    import jwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False

logger = logging.getLogger(__name__)

# Configurable parameters
DEFAULT_RATE_LIMIT = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
DEFAULT_RATE_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key")
ALGORITHM = "HS256"

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limit middleware using Redis.
    Rate limits are enforced per-tenant and per-user.
    """
    def __init__(
        self, 
        app, 
        redis_url: str = REDIS_URL,
        limit: int = DEFAULT_RATE_LIMIT,
        window: int = DEFAULT_RATE_WINDOW
    ):
        super().__init__(app)
        self.limit = limit
        self.window = window
        self.redis_url = redis_url
        self._redis_client = None

    @property
    def redis_client(self):
        if not HAS_REDIS:
            return None
        if self._redis_client is None:
            self._redis_client = redis.from_url(self.redis_url)
        return self._redis_client

    async def dispatch(self, request: Request, call_next) -> Response:
        redis_conn = self.redis_client
        if not HAS_REDIS or not redis_conn:
            logger.warning("Redis is not available; rate limiting is disabled.")
            return await call_next(request)
            
        # Retrieve tenant_id, which is populated by TenantMiddleware
        tenant_id = getattr(request.state, "tenant_id", "default-tenant")
        user_id = self.extract_user_id(request)
        
        # Rate limit key per tenant and user
        key = f"rate_limit:{tenant_id}:{user_id}"
        
        current_time = time.time()
        window_start = current_time - self.window
        
        try:
            # First pipeline: get current count and cleanup old entries
            async with redis_conn.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                results = await pipe.execute()
                
            request_count = results[1]
            
            if request_count >= self.limit:
                return JSONResponse(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Rate limit exceeded.",
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "window": self.window,
                        "limit": self.limit
                    }
                )
            
            # Second pipeline: add request only if successful
            async with redis_conn.pipeline(transaction=True) as pipe:
                pipe.zadd(key, {str(current_time): current_time})
                pipe.expire(key, self.window)
                await pipe.execute()
                
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # Fail open if Redis fails
            pass

        return await call_next(request)

    def extract_user_id(self, request: Request) -> str:
        # We no longer parse unverified JWTs to extract user_id. 
        # Rely on API Key, IP or properly authenticated user in state if available.
        if hasattr(request.state, "user") and request.state.user:
            return request.state.user.get("identity", "anonymous")
        
        # Fallback to API Key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"apikey:{api_key}"
            
        # Fallback to Client IP
        if request.client and request.client.host:
            return f"ip:{request.client.host}"
            
        return "anonymous"
