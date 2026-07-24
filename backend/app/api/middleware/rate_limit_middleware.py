import os
import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)

# Read Redis URI from env so limits are shared across all replicas.
# Falls back to memory:// only when explicitly set (e.g., unit tests).
# In production this MUST point to a Redis instance.
_storage_uri = os.getenv("RATE_LIMIT_STORAGE_URI", "redis://redis:6379")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=_storage_uri,
)

if _storage_uri.startswith("memory://"):
    logger.warning(
        "rate_limit_memory_backend",
        reason="RATE_LIMIT_STORAGE_URI not set to Redis — limits are per-instance only, NOT shared across replicas",
    )


async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    logger.warning(
        "rate_limit_exceeded",
        client_ip=get_remote_address(request),
        path=request.url.path,
        limit=str(exc.detail),
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down.",
            "retry_after": str(exc.detail),
        },
    )
