import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.logger import setup_logging, logger
from app.api.middleware.auth_middleware import DualAuthMiddleware
from app.api.middleware.trace_middleware import TraceMiddleware
from app.api.middleware.audit_middleware import AuditMiddleware
from app.api.middleware.rate_limit_middleware import limiter, _rate_limit_exceeded_handler
from app.application.audit_logger import audit_logger

# Initialize structured logging
setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", project=settings.PROJECT_NAME, version=settings.VERSION)
    await run_db_migrations()
    await audit_logger.start()
    scan_task = asyncio.create_task(_detection_scan_loop())
    yield
    scan_task.cancel()
    await audit_logger.stop()
    logger.info("shutdown", project=settings.PROJECT_NAME)


async def _detection_scan_loop() -> None:
    """Background Phase 2 detection: scan every tenant's new telemetry.

    Runs inside the API process (no extra infra). Each scan resumes from
    the per-tenant watermark, so restarts never double-scan. Failures are
    logged and retried on the next interval — a bad scan must never kill
    the API.
    """
    import asyncio as _asyncio

    from sqlalchemy import select as _select

    from app.detection.engine import scan_tenant as _scan_tenant
    from app.domain.models import Tenant as _Tenant
    from app.infrastructure.database import AsyncSessionLocal as _SessionLocal

    interval = int(os.environ.get("DETECTION_SCAN_INTERVAL_S", "300"))
    # Let the app finish starting before the first pass.
    await _asyncio.sleep(60)
    while True:
        try:
            async with _SessionLocal() as db:
                tenant_ids = list((await db.execute(_select(_Tenant.id))).scalars().all())
            for tid in tenant_ids:
                try:
                    async with _SessionLocal() as db:
                        result = await _scan_tenant(db, tid)
                    logger.info("detection_scan_complete", tenant_id=tid,
                                events=result["events_scanned"], alerts=result["alerts_created"])
                except Exception:
                    logger.error("detection_scan_failed", tenant_id=tid, exc_info=True)
        except Exception:
            logger.error("detection_scan_loop_error", exc_info=True)
        await _asyncio.sleep(interval)


async def run_db_migrations() -> None:
    """Apply pending Alembic migrations on startup.

    Render's free tier does not support preDeployCommand, so migrations run
    here instead. Alembic is idempotent: a fully-migrated database is a
    no-op. A failed migration raises and blocks the deploy from going live.
    """
    import asyncio
    import os
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent  # backend/
    db_url = os.getenv("DATABASE_URL", os.getenv("POSTGRES_URL", ""))
    if not db_url:
        # Local-dev SQLite fallback: no alembic, just create tables.
        from app.domain.models import Base
        from app.infrastructure.storage.engine import engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("db_tables_created_sqlite_fallback")
        return
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
        logger.info("db_migrations_applied")
    except Exception:
        logger.error("db_migration_failed", exc_info=True)
        raise

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        version=settings.VERSION,
        lifespan=lifespan
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(TraceMiddleware)
    app.add_middleware(DualAuthMiddleware)
    app.add_middleware(AuditMiddleware)

    # CORS must be the outermost middleware so preflight requests are
    # handled before auth. Origins are env-driven (BACKEND_CORS_ORIGINS,
    # comma-separated) so the Vercel frontend can call this API.
    # Preview deployments get per-commit URLs, so we additionally allow
    # this project's own Vercel preview subdomains via regex. The pattern
    # is scoped to ai-soc-2-frontend-* so no other Vercel site is trusted.
    cors_origins = [o.strip() for o in settings.BACKEND_CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=r"https://ai-soc-2-frontend-[a-z0-9-]+\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Versioning Router
    api_router = APIRouter()
    from app.api.v1 import api_keys, notifications, compliance, auth, incidents, alerts, stub_routes, ml_routes, integrations, agents, onboarding, dashboard, events
    from app.detection import api as detection_api
    
    @api_router.get("/health", tags=["System"])
    async def health_check():
        logger.info("health_check_called", endpoint="/health")
        return {"status": "ok", "version": settings.VERSION}

    api_router.include_router(api_keys.router, prefix="/api-keys", tags=["API Keys"])
    api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
    api_router.include_router(compliance.router, prefix="/compliance", tags=["Compliance"])
    api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
    api_router.include_router(incidents.router, prefix="/incidents", tags=["Incidents"])
    api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
    api_router.include_router(stub_routes.router, tags=["Stubs"])
    api_router.include_router(ml_routes.router, tags=["ML"])
    api_router.include_router(integrations.router, prefix="/integrations", tags=["Integrations"])
    api_router.include_router(agents.router, prefix="/agents", tags=["Endpoint Agents"])
    api_router.include_router(onboarding.router, prefix="/onboarding", tags=["Onboarding"])
    api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
    api_router.include_router(events.router, prefix="/events", tags=["Security Events"])
    api_router.include_router(detection_api.router, prefix="/detection", tags=["Detection"])

    app.include_router(api_router, prefix=settings.API_V1_STR)

    @app.get("/", tags=["System"], include_in_schema=False)
    async def root():
        return {
            "service": "AI SOC Backend",
            "version": settings.VERSION,
            "status": "ok",
            "api": settings.API_V1_STR,
            "health": f"{settings.API_V1_STR}/health",
            "docs": "/docs",
        }

    return app

app = create_app()
