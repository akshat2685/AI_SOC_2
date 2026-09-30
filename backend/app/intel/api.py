"""Threat-intel API: refresh status + manual refresh trigger.

Mounted by the parent at /api/v1/intel (see main.py) — this module only
defines the router.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict

from app.api.deps import require_roles_dual
from app.api.middleware.rate_limit_middleware import limiter
from app.application.audit_logger import audit_logger
from app.core.auth import current_tenant_id, current_trace_id, current_user_id
from app.domain.models import RoleEnum
from app.infrastructure.database import get_db
from app.intel.models import ThreatIntelIoC
from app.intel.refresh import last_refresh_info, refresh_all

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]


@router.get("/status")
@limiter.limit("60/minute")
async def intel_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
) -> Dict[str, Any]:
    """IoC counts by source/type plus per-source last refresh state.

    Intel is global (not tenant-scoped): every tenant sees the same feed.
    """
    rows = (
        (await db.execute(
            select(
                ThreatIntelIoC.source,
                ThreatIntelIoC.ioc_type,
                func.count(ThreatIntelIoC.id),
            ).group_by(ThreatIntelIoC.source, ThreatIntelIoC.ioc_type)
        ))
        .all()
    )
    by_source: Dict[str, Dict[str, Any]] = {}
    total = 0
    for source, ioc_type, count in rows:
        entry = by_source.setdefault(source, {"total": 0, "by_type": {}})
        entry["by_type"][ioc_type] = count
        entry["total"] += count
        total += count

    refresh = last_refresh_info()
    for source, entry in by_source.items():
        entry["last_refresh_at"] = refresh.get(source, {}).get("last_refresh_at")
        entry["last_error"] = refresh.get(source, {}).get("last_error")
    # Sources that errored before storing anything still show up.
    for source, info in refresh.items():
        if source not in by_source:
            by_source[source] = {
                "total": 0,
                "by_type": {},
                "last_refresh_at": info["last_refresh_at"],
                "last_error": info["last_error"],
            }

    return {
        "total_iocs": total,
        "sources": by_source,
        "note": "intel is global across tenants",
    }


@router.post("/refresh")
@limiter.limit("5/minute")
async def trigger_refresh(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
) -> Dict[str, Any]:
    """Run a full intel refresh now. One dead feed is recorded, not fatal."""
    tenant_id = current_tenant_id.get() or 1
    try:
        result = await refresh_all(db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Intel refresh failed: {exc}",
        )

    audit_logger.emit(
        action="intel_refresh",
        tenant_id=tenant_id,
        user_id=current_user_id.get(),
        trace_id=current_trace_id.get(),
        details={
            "inserted": result["totals"]["inserted"],
            "updated": result["totals"]["updated"],
            "sources": {
                name: info["status"] for name, info in result["sources"].items()
            },
        },
    )
    return result
