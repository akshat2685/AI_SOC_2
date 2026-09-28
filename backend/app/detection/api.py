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
    lookback_hours: int | None = None,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
) -> Dict[str, Any]:
    """Run the detection engine over new telemetry for the current tenant.

    Pass ?lookback_hours=N to re-scan the trailing N hours instead of
    resuming from the watermark (dedup stretches to match).
    """
    tenant_id = current_tenant_id.get() or 1
    try:
        result = await scan_tenant(db, tenant_id, lookback_hours=lookback_hours)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
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
    """Last scan watermark and totals for the current tenant.

    `stale` is True when the background scan loop has not completed a scan
    within 2x its configured interval — the loop may be dead even though the
    API is up. `scan_interval_s` reports the configured cadence so the UI can
    label it honestly instead of claiming "real-time".
    """
    import os
    from datetime import datetime, timezone

    tenant_id = current_tenant_id.get() or 1
    wm = await db.get(DetectionWatermark, tenant_id)
    last_scan_at = wm.last_scan_at if wm and wm.last_scan_at else None
    interval_s = int(os.environ.get("DETECTION_SCAN_INTERVAL_S", "300"))
    stale = True
    if last_scan_at is not None:
        now = datetime.now(timezone.utc)
        ts = last_scan_at if last_scan_at.tzinfo else last_scan_at.replace(tzinfo=timezone.utc)
        stale = (now - ts).total_seconds() > 2 * interval_s
    return {
        "tenant_id": tenant_id,
        "last_scan_at": last_scan_at.isoformat() if last_scan_at else None,
        "events_scanned_total": (wm.events_scanned if wm else 0) or 0,
        "alerts_created_total": (wm.alerts_created if wm else 0) or 0,
        "engine": "detection-v1",
        "scan_interval_s": interval_s,
        "stale": stale,
    }
