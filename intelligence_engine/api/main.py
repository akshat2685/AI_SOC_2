import asyncio
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

try:
    from core.logging_config import setup_logging
except ImportError:
    from intelligence_engine.core.logging_config import setup_logging

try:
    from api.middleware.trace_middleware import TraceMiddleware
except ImportError:
    from intelligence_engine.api.middleware.trace_middleware import TraceMiddleware

try:
    from api.middleware.exception_handler import global_exception_handler
except ImportError:
    from intelligence_engine.api.middleware.exception_handler import global_exception_handler

try:
    from api.middleware.tenant import TenantMiddleware, APIVersioningMiddleware
except ImportError:
    from intelligence_engine.api.middleware.tenant import TenantMiddleware, APIVersioningMiddleware


try:
    from api.routes import (
        health,
        copilot,
        investigations,
        alerts,
        connectors,
        playbooks,
        reports,
        dashboard,
        approvals,
    )
    from core.config import get_settings
    from api.middleware.auth import require_permission, get_current_user
except ImportError:
    from intelligence_engine.api.routes import (
        health,
        copilot,
        investigations,
        alerts,
        connectors,
        playbooks,
        reports,
        dashboard,
        approvals,
    )
    from intelligence_engine.core.config import get_settings
    from intelligence_engine.api.middleware.auth import require_permission, get_current_user

try:
    from kafka_consumer import consume_events, dlq_consumer_task
except ImportError:
    try:
        from intelligence_engine.kafka_consumer import consume_events, dlq_consumer_task
    except ImportError:
        consume_events = None
        dlq_consumer_task = None

try:
    from api.database import db
except ImportError:
    from intelligence_engine.api.database import db

logger = logging.getLogger(__name__)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Set up logging on app startup
    setup_logging()
    logger.info("Logging configured on app startup via setup_logging().")

    # Start Kafka consumer as a background task when the app starts if available
    consumer_task = None
    dlq_task = None
    if consume_events is not None:
        try:
            consumer_task = asyncio.create_task(consume_events())
            logger.info("Kafka consumer background task started via lifespan.")
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer background task: {e}")
            
    if dlq_consumer_task is not None:
        try:
            dlq_task = asyncio.create_task(dlq_consumer_task())
            logger.info("Kafka DLQ consumer background task started via lifespan.")
        except Exception as e:
            logger.error(f"Failed to start Kafka DLQ consumer background task: {e}")
    else:
        logger.warning("Kafka consumer (consume_events) not available. Background consumer task skipped.")
        
    yield
    
    # Cancel the task when the app shuts down
    if consumer_task:
        consumer_task.cancel()
        logger.info("Kafka consumer background task cancelled.")
        
    if dlq_task:
        dlq_task.cancel()
        logger.info("Kafka DLQ consumer background task cancelled.")

    # Clean up and close all database connections
    try:
        db.close_all()
        logger.info("All database connections successfully closed.")
    except Exception as e:
        logger.error(f"Error closing database connections during lifespan shutdown: {e}")

tags_metadata = [
    {"name": "health", "description": "System health checks and readiness."},
    {"name": "copilot", "description": "AI-driven SOC copilot interactions."},
    {"name": "investigations", "description": "Manage incident investigations."},
    {"name": "alerts", "description": "SOC alerts ingestion and processing."},
    {"name": "connectors", "description": "Third-party SIEM/EDR connectors."},
    {"name": "playbooks", "description": "Automated response playbooks."},
    {"name": "reports", "description": "Generate compliance and threat reports."},
    {"name": "dashboard", "description": "SOC metrics and dashboard data."},
]

app = FastAPI(
    title="EDYSOR-X Intelligence Engine API",
    description="Autonomous SOC Production FastAPI Backend",
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata
)

# Exception Handler
app.add_exception_handler(Exception, global_exception_handler)

class SecureHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecureHeadersMiddleware)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["*"] # Ideally configure this based on env
)
app.add_middleware(TraceMiddleware)
app.add_middleware(APIVersioningMiddleware, version="2.0.0")
app.add_middleware(TenantMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.security.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Include the 8 APIRouters under /api/v1 with RBAC
app.include_router(health.router, prefix="/api/v1") # Health unauthenticated
app.include_router(copilot.router, prefix="/api/v1", dependencies=[Depends(require_permission("read"))])
app.include_router(investigations.router, prefix="/api/v1", dependencies=[Depends(require_permission("read"))])
app.include_router(alerts.router, prefix="/api/v1", dependencies=[Depends(require_permission("read"))])
app.include_router(connectors.router, prefix="/api/v1", dependencies=[Depends(require_permission("manage_settings"))])
app.include_router(playbooks.router, prefix="/api/v1", dependencies=[Depends(require_permission("execute"))])
app.include_router(reports.router, prefix="/api/v1", dependencies=[Depends(require_permission("read"))])
app.include_router(dashboard.router, prefix="/api/v1", dependencies=[Depends(require_permission("read"))])
app.include_router(approvals.router, prefix="/api/v1", dependencies=[Depends(require_permission("write"))])

# Also include without prefix for root-level routes
app.include_router(health.router)
app.include_router(copilot.router, dependencies=[Depends(require_permission("read"))])
app.include_router(investigations.router, dependencies=[Depends(require_permission("read"))])
app.include_router(alerts.router, dependencies=[Depends(require_permission("read"))])
app.include_router(connectors.router, dependencies=[Depends(require_permission("manage_settings"))])
app.include_router(playbooks.router, dependencies=[Depends(require_permission("execute"))])
app.include_router(reports.router, dependencies=[Depends(require_permission("read"))])
app.include_router(dashboard.router, dependencies=[Depends(require_permission("read"))])
app.include_router(approvals.router, dependencies=[Depends(require_permission("write"))])

@app.get("/")
async def root():
    return {
        "message": "Welcome to the EDYSOR-X Production FastAPI Gateway",
        "docs_url": "/docs"
    }

@app.get("/api/v1/trigger-error")
async def trigger_error(user = Depends(require_permission("read"))):
    raise ValueError("Test unhandled exception")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=settings.api.intelligence_engine_host,
        port=settings.api.intelligence_engine_port,
        reload=True
    )
