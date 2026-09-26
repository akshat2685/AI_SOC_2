"""Detection API: manual scan trigger + scan status.

The scan loop also runs automatically in the background (see main.py
lifespan); these endpoints expose the same scan_tenant() on demand.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict

from app.api.deps import require_roles_dual
from app.api.middleware.rate_limit_middleware import limiter
from app.application.audit_logger import audit_logger
from app.core.auth import current_tenant_id, current_trace_id, current_user_id
from app.detection.engine import scan_tenant
from app.domain.models import DetectionWatermark, RoleEnum
from app.infrastructure.database import get_db

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]


@router.post("/scan")
@limiter.limit("10/minute")
async def trigger_scan(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
) -> Dict[str, Any]:
    """Run the detection engine over new telemetry for the current tenant."""
    tenant_id = current_tenant_id.get() or 1
    try:
        result = await scan_tenant(db, tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Detection scan failed: {exc}")

    audit_logger.emit(
        action="detection_scan",
        tenant_id=tenant_id,
        user_id=current_user_id.get(),
        trace_id=current_trace_id.get(),
        details={
            "events_scanned": result["events_scanned"],
            "alerts_created": result["alerts_created"],
        },
    )
    return result


@router.get("/status")
@limiter.limit("60/minute")
async def scan_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
) -> Dict[str, Any]:
    """Last scan watermark and totals for the current tenant."""
    tenant_id = current_tenant_id.get() or 1
    wm = await db.get(DetectionWatermark, tenant_id)
    return {
        "tenant_id": tenant_id,
        "last_scan_at": wm.last_scan_at.isoformat() if wm and wm.last_scan_at else None,
        "events_scanned_total": (wm.events_scanned if wm else 0) or 0,
        "alerts_created_total": (wm.alerts_created if wm else 0) or 0,
        "engine": "detection-v1",
    }
