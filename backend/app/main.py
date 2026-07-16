from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from app.core.config import settings
from app.core.logger import setup_logging, logger

# Initialize structured logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", project=settings.PROJECT_NAME, version=settings.VERSION)
    yield
    logger.info("shutdown", project=settings.PROJECT_NAME)

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        version=settings.VERSION,
        lifespan=lifespan
    )

    # API Versioning Router
    api_router = APIRouter()
    
    @api_router.get("/health", tags=["System"])
    async def health_check():
        logger.info("health_check_called", endpoint="/health")
        return {"status": "ok", "version": settings.VERSION}

    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app

app = create_app()
