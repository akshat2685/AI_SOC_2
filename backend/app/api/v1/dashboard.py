"""SOC Command Center: tenant-scoped aggregate view.

All numbers are simple counts from the tenant's own tables. Agent status is
computed from heartbeat age (same derivation as /agents). Nothing here is
a fabricated score — where a number is derived rather than counted, it is
labeled.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.core.auth import current_tenant_id
from app.domain.models import (
    Alert,
    ApprovalRequest,
    ApprovalStatusEnum,
    EndpointAgent,
    Incident,
    Integration,
    RoleEnum,
    SeverityEnum,
)
from app.infrastructure.database import get_db

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]

ONLINE_THRESHOLD_S = 90
DEGRADED_THRESHOLD_S = 300


def _effective_agent_status(last_heartbeat_at) -> str:
    if last_heartbeat_at is None:
        return "unregistered"
    hb = last_heartbeat_at
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - hb).total_seconds()
    if age < 0:
        return "online"
    if age <= ONLINE_THRESHOLD_S:
        return "online"
    if age <= DEGRADED_THRESHOLD_S:
        return "degraded"
    return "offline"


@router.get("/soc-command")
async def soc_command(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1

    inc_rows = (
        await db.execute(
            select(Incident.severity, func.count(Incident.id))
            .where(Incident.tenant_id == tenant_id)
            .group_by(Incident.severity)
        )
    ).all()
    incidents_by_severity: Dict[str, int] = {}
    for sev, count in inc_rows:
        key = sev.value if isinstance(sev, SeverityEnum) else str(sev)
        incidents_by_severity[key] = count

    alert_total = (
        await db.execute(select(func.count(Alert.id)).where(Alert.tenant_id == tenant_id))
    ).scalar() or 0

    agents = (
        await db.execute(select(EndpointAgent).where(EndpointAgent.tenant_id == tenant_id))
    ).scalars().all()
    agents_by_status: Dict[str, int] = {}
    for a in agents:
        st = _effective_agent_status(a.last_heartbeat_at)
        agents_by_status[st] = agents_by_status.get(st, 0) + 1

    int_rows = (
        await db.execute(
            select(Integration.status, func.count(Integration.id))
            .where(Integration.tenant_id == tenant_id)
            .group_by(Integration.status)
        )
    ).all()
    integrations_by_status: Dict[str, int] = {}
    for st, count in int_rows:
        key = st.value if hasattr(st, "value") else str(st)
        integrations_by_status[key] = count

    open_approvals = (
        await db.execute(
            select(func.count(ApprovalRequest.id)).where(
                ApprovalRequest.tenant_id == tenant_id,
                ApprovalRequest.status == ApprovalStatusEnum.PENDING,
            )
        )
    ).scalar() or 0

    return {
        "incidents_by_severity": incidents_by_severity,
        "total_incidents": sum(incidents_by_severity.values()),
        "total_alerts": alert_total,
        "agents": {
            "total": len(agents),
            "by_status": agents_by_status,
            "status_note": "Computed from heartbeat age at read time: online <90s, degraded <5min, offline beyond that.",
        },
        "integrations_by_status": integrations_by_status,
        "total_integrations": sum(integrations_by_status.values()),
        "open_approvals": open_approvals,
    }
