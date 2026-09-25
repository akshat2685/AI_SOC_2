import os
import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = structlog.get_logger(__name__)

# Read Redis URI from env so limits are shared across all replicas.
# Defaults to memory:// (per-instance limits) when Redis isn't configured --
# the MVP deploys without Redis, so rate limiting must not hard-fail.
# Set RATE_LIMIT_STORAGE_URI=redis://<host>:6379 to share limits across replicas.
_storage_uri = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=_storage_uri,
)

if _storage_uri.startswith("memory://"):
    logger.warning(
        "rate_limit_memory_backend",
        reason="RATE_LIMIT_STORAGE_URI not set to Redis -- limits are per-instance only, NOT shared across replicas. "
        "Set RATE_LIMIT_STORAGE_URI=redis://<host>:6379 to enable shared rate limiting.",
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
