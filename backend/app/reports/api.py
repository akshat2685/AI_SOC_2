"""Incident report download endpoint.

NOTE (wiring): this router is standalone — the parent must mount it, e.g.
    from app.reports.api import router as incident_report_router
    api_router.include_router(incident_report_router, prefix="/incidents", tags=["Incidents"])
main.py is intentionally untouched by this change.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.api.middleware.rate_limit_middleware import limiter
from app.application.audit_logger import audit_logger
from app.core.auth import current_tenant_id, current_trace_id, current_user_id
from app.domain.models import Incident, RoleEnum
from app.infrastructure.database import get_db
from app.reports.incident_report import REPORT_VERSION, build_incident_report

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]


@router.get("/{incident_id}/report")
@limiter.limit("10/minute")
async def download_incident_report(
    request: Request,
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Download the markdown incident report as a file. 404 when the
    incident doesn't exist or belongs to another tenant."""
    tenant_id = current_tenant_id.get() or 1
    exists = (await db.execute(
        select(Incident.id).where(
            Incident.id == incident_id, Incident.tenant_id == tenant_id
        )
    )).scalars().first()
    if not exists:
        raise HTTPException(status_code=404, detail="Incident not found")

    try:
        markdown = await build_incident_report(db, incident_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found")

    audit_logger.emit(
        action="incident_report_downloaded",
        tenant_id=tenant_id,
        user_id=current_user_id.get(),
        trace_id=current_trace_id.get(),
        details={"incident_id": incident_id, "report_version": REPORT_VERSION},
    )
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=incident-{incident_id}-report.md"
        },
    )
