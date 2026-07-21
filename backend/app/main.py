from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from app.core.config import settings
from app.core.logger import setup_logging, logger
from app.api.middleware.auth_middleware import DualAuthMiddleware
from app.api.middleware.trace_middleware import TraceMiddleware
from app.api.middleware.audit_middleware import AuditMiddleware
from app.application.audit_logger import audit_logger
from app.api.v1 import api_keys, notifications

# Initialize structured logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", project=settings.PROJECT_NAME, version=settings.VERSION)
    await audit_logger.start()
    yield
    await audit_logger.stop()
    logger.info("shutdown", project=settings.PROJECT_NAME)

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        version=settings.VERSION,
        lifespan=lifespan
    )

    app.add_middleware(TraceMiddleware)
    app.add_middleware(DualAuthMiddleware)
    app.add_middleware(AuditMiddleware)

    # API Versioning Router
    api_router = APIRouter()
    from app.api.v1 import api_keys, notifications, compliance
    
    @api_router.get("/health", tags=["System"])
    async def health_check():
        logger.info("health_check_called", endpoint="/health")
        return {"status": "ok", "version": settings.VERSION}

    api_router.include_router(api_keys.router, prefix="/api-keys", tags=["API Keys"])
    api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
    api_router.include_router(compliance.router, prefix="/compliance", tags=["Compliance"])

    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app

app = create_app()
