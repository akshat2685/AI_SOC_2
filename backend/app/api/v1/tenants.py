"""Per-tenant safety settings: autonomous response posture + sensor cadence.

GET  /tenants/me/settings  (any authenticated role) — read the tenant's
                           response_mode and poll_interval_s.
PUT  /tenants/me/settings  (TENANT_ADMIN only) — change them.

response_mode controls what the autonomous response engine (see
app/response/policy.py) is allowed to do:
  dry_run        — observe only; the engine audits what it WOULD have done.
  approvals_only — every actionable alert goes to a human approval queue.
  auto_contain   — rules-based HIGH/CRITICAL + confidence >= 80 may execute
                   containment commands autonomously.

New tenants are created in dry_run; switching to auto_contain is an explicit,
audited admin decision.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.application.audit_logger import audit_logger
from app.core.auth import current_tenant_id, current_user_id, current_trace_id
from app.domain.models import RoleEnum, Tenant
from app.infrastructure.database import get_db

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
ADMIN_ROLES = [RoleEnum.TENANT_ADMIN]

RESPONSE_MODES = ("dry_run", "approvals_only", "auto_contain")
POLL_MIN_S, POLL_MAX_S = 10, 600


class TenantSettingsUpdate(BaseModel):
    response_mode: Optional[str] = Field(
        default=None, description="One of dry_run | approvals_only | auto_contain"
    )
    poll_interval_s: Optional[int] = Field(
        default=None, ge=POLL_MIN_S, le=POLL_MAX_S,
        description=f"Sensor command-poll cadence, {POLL_MIN_S}-{POLL_MAX_S} seconds",
    )


def _settings_dict(t: Tenant) -> Dict[str, Any]:
    return {
        "tenant_id": t.id,
        "name": t.name,
        "response_mode": t.response_mode,
        "poll_interval_s": t.poll_interval_s,
        "response_modes": list(RESPONSE_MODES),
    }


@router.get("/me/settings")
async def get_tenant_settings(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = current_tenant_id.get()
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _settings_dict(tenant)


@router.put("/me/settings")
async def put_tenant_settings(
    data: TenantSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(ADMIN_ROLES)),
):
    tenant_id = current_tenant_id.get()
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    changes: Dict[str, Any] = {}
    if data.response_mode is not None:
        if data.response_mode not in RESPONSE_MODES:
            raise HTTPException(
                status_code=422,
                detail=f"response_mode must be one of {list(RESPONSE_MODES)}",
            )
        if tenant.response_mode != data.response_mode:
            changes["response_mode"] = {"from": tenant.response_mode, "to": data.response_mode}
            tenant.response_mode = data.response_mode
    if data.poll_interval_s is not None:
        if tenant.poll_interval_s != data.poll_interval_s:
            changes["poll_interval_s"] = {"from": tenant.poll_interval_s, "to": data.poll_interval_s}
            tenant.poll_interval_s = data.poll_interval_s

    if changes:
        await db.commit()
        await db.refresh(tenant)
        audit_logger.emit(
            "tenant_settings_changed",
            tenant_id=tenant_id,
            user_id=current_user_id.get(),
            trace_id=current_trace_id.get(),
            details={"changes": changes},
        )

    return _settings_dict(tenant)
