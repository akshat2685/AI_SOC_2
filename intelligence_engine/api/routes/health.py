from fastapi import APIRouter

try:
    from core.health import HealthChecker
except ImportError:
    from intelligence_engine.core.health import HealthChecker

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    checker = HealthChecker()
    return await checker.aggregate()

@router.get("/health/live")
async def health_live():
    return {"status": "alive"}

@router.get("/health/ready")
async def health_ready():
    checker = HealthChecker()
    return await checker.aggregate()
