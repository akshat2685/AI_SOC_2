import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import os

try:
    import jwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False

logger = structlog.get_logger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required for TenantMiddleware.")
ALGORITHM = "HS256"
DEFAULT_TENANT_ID = "default-tenant"

class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract tenant_id from JWT or X-Tenant-ID header 
    and securely inject it into the request state for use in downstream queries.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = self.extract_tenant_id(request)
        request.state.tenant_id = tenant_id
        
        response = await call_next(request)
        return response

    def extract_tenant_id(self, request: Request) -> str:
        # We no longer extract tenant_id from unverified JWTs (Header Spoofing vulnerability).
        # AuthenticationService (DI) handles secure tenant validation.
        # Fallback to header or default for unauthenticated pre-auth middleware requests
        
        x_tenant_id = request.headers.get("X-Tenant-ID")
        if x_tenant_id:
            return x_tenant_id
        
        return DEFAULT_TENANT_ID

class APIVersioningMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle API versioning strategies, setting standard version headers
    and deprecation headers where applicable.
    """
    def __init__(self, app, version: str = "2.0.0", deprecated_paths: dict = None):
        super().__init__(app)
        self.version = version
        self.deprecated_paths = deprecated_paths or {
            "/api/v1/old-endpoint": {
                "deprecation_date": "Wed, 21 Oct 2026 07:28:00 GMT",
                "sunset_date": "Wed, 21 Oct 2027 07:28:00 GMT",
                "link": '<https://api.edysor-x.com/v2/new-endpoint>; rel="successor-version"'
            }
        }

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Inject standard API Version
        response.headers["X-API-Version"] = self.version
        
        path = request.url.path
        
        # Check if current path matches any deprecated path
        for dep_path, info in self.deprecated_paths.items():
            if path.startswith(dep_path):
                if "deprecation_date" in info:
                    response.headers["Deprecation"] = info["deprecation_date"]
                else:
                    response.headers["Deprecation"] = "true"
                    
                if "sunset_date" in info:
                    response.headers["Sunset"] = info["sunset_date"]
                if "link" in info:
                    response.headers["Link"] = info["link"]
                
                response.headers["Warning"] = '299 - "This API endpoint is deprecated."'
                break

        return response
