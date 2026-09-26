"""EDYSOR onboarding wizard state (per tenant)."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.core.auth import current_tenant_id
from app.domain.models import OnboardingState, RoleEnum
from app.infrastructure.database import get_db

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]


def _tenant_id() -> int:
    return current_tenant_id.get() or 1


def _onboarding_to_dict(s: Optional[OnboardingState], tenant_id: int) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "current_step": s.current_step if s else 0,
        "completed_steps": s.completed_steps if s and s.completed_steps else [],
        "skipped_steps": s.skipped_steps if s and s.skipped_steps else [],
        "updated_at": s.updated_at.isoformat() if s and s.updated_at else None,
    }


@router.get("/state")
async def get_onboarding_state(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Return the tenant's onboarding wizard progress (defaults if never started)."""
    tenant_id = _tenant_id()
    result = await db.execute(select(OnboardingState).where(OnboardingState.tenant_id == tenant_id))
    state = result.scalars().first()
    return _onboarding_to_dict(state, tenant_id)


@router.put("/state")
async def put_onboarding_state(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    """Create or update the tenant's onboarding wizard progress."""
    tenant_id = _tenant_id()
    result = await db.execute(select(OnboardingState).where(OnboardingState.tenant_id == tenant_id))
    state = result.scalars().first()
    if not state:
        state = OnboardingState(tenant_id=tenant_id)
        db.add(state)

    if "current_step" in data:
        try:
            state.current_step = max(0, int(data["current_step"]))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="current_step must be an integer.")
    if "completed_steps" in data:
        if not isinstance(data["completed_steps"], list):
            raise HTTPException(status_code=400, detail="completed_steps must be a list.")
        state.completed_steps = data["completed_steps"]
    if "skipped_steps" in data:
        if not isinstance(data["skipped_steps"], list):
            raise HTTPException(status_code=400, detail="skipped_steps must be a list.")
        state.skipped_steps = data["skipped_steps"]

    await db.commit()
    await db.refresh(state)
    return _onboarding_to_dict(state, tenant_id)
