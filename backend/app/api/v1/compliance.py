from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional

from app.infrastructure.database import get_db
from app.domain.models import ComplianceFramework, ComplianceViolation, ComplianceControl, ComplianceRule
from app.api.deps import get_current_user_dual
from app.core.auth import current_tenant_id

router = APIRouter()

class ComplianceFrameworkResponse(BaseModel):
    id: int
    name: str
    version: str
    description: Optional[str] = None

class CompliancePostureResponse(BaseModel):
    score: float
    total_controls: int
    failed_controls: int
    violations: List[dict]

@router.get("/frameworks", response_model=List[ComplianceFrameworkResponse])
async def list_frameworks(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_dual)
) -> Any:
    tenant_id = current_tenant_id.get()
    result = await db.execute(select(ComplianceFramework).where(ComplianceFramework.tenant_id == tenant_id))
    return result.scalars().all()

@router.get("/posture", response_model=CompliancePostureResponse)
async def get_posture(
    db: AsyncSession = Depends(get_db),
    user_id: int = Depends(get_current_user_dual)
) -> Any:
    tenant_id = current_tenant_id.get()
    
    # Calculate score simply: (total - failed) / total * 100
    controls_result = await db.execute(
        select(func.count(ComplianceControl.id))
        .join(ComplianceFramework)
        .where(ComplianceFramework.tenant_id == tenant_id)
    )
    total_controls = controls_result.scalar() or 0

    violations_result = await db.execute(
        select(ComplianceViolation)
        .where(ComplianceViolation.tenant_id == tenant_id, ComplianceViolation.status == "OPEN")
    )
    violations = violations_result.scalars().all()
    
    failed_rule_ids = {v.rule_id for v in violations}
    failed_controls = 0
    if failed_rule_ids:
        failed_controls_result = await db.execute(
            select(func.count(func.distinct(ComplianceRule.control_id)))
            .where(ComplianceRule.id.in_(list(failed_rule_ids)))
        )
        failed_controls = failed_controls_result.scalar() or 0
        
    score = 100.0
    if total_controls > 0:
        score = max(0.0, ((total_controls - failed_controls) / total_controls) * 100.0)

    return {
        "score": score,
        "total_controls": total_controls,
        "failed_controls": failed_controls,
        "violations": [{"id": v.id, "rule_id": v.rule_id, "status": v.status, "detected_at": v.detected_at.isoformat()} for v in violations]
    }
