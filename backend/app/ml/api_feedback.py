"""Feedback endpoints for the self-learning retrain loop.

Analysts submit labeled feature vectors (or resolve incidents with a
verdict, which auto-records via the incidents hook); the standalone
retrain script consumes the stored rows under a regression gate.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.api.middleware.rate_limit_middleware import limiter
from app.application.audit_logger import audit_logger
from app.core.auth import current_tenant_id, current_user_id
from app.domain.models import RoleEnum, TrainingFeedback
from app.infrastructure.database import get_db
from app.ml.feedback import SEVERITIES, _expand_vector

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]


@router.post("/ml/feedback")
@limiter.limit("10/minute")
async def submit_feedback(
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    """Manually submit one labeled feature vector (analyst+).

    Body: {"feature_vector": {15 features}, "label": "attack"|"benign",
           "technique_id"?: str, "tactic"?: str, "severity"?: str,
           "incident_id"?: int, "device_id"?: str}
    Stored with source="analyst-verdict".
    """
    tenant_id = current_tenant_id.get() or 1
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Provide a JSON object.")
    label = str(body.get("label", "")).lower()
    if label not in ("attack", "benign"):
        raise HTTPException(status_code=400,
                            detail="label must be 'attack' or 'benign'")
    severity = str(body.get("severity") or "MEDIUM").upper()
    if severity not in SEVERITIES:
        raise HTTPException(
            status_code=400,
            detail=f"severity must be one of {list(SEVERITIES)}")

    incident_id = body.get("incident_id")
    if incident_id is not None:
        try:
            incident_id = int(incident_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400,
                                detail="incident_id must be an integer")

    row = TrainingFeedback(
        tenant_id=tenant_id,
        incident_id=incident_id,
        device_id=(str(body.get("device_id"))[:64]
                   if body.get("device_id") else None),
        feature_vector=_expand_vector(body.get("feature_vector") or {}),
        label=label,
        technique_id=(str(body.get("technique_id"))[:20]
                      if body.get("technique_id") else None),
        tactic=(str(body.get("tactic"))[:50]
                if body.get("tactic") else None),
        severity=severity,
        source="analyst-verdict",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    audit_logger.emit(
        action="ml_feedback_submit",
        tenant_id=tenant_id,
        user_id=current_user_id.get(),
        details={"feedback_id": row.id, "label": label,
                 "incident_id": incident_id},
    )
    return {"status": "success", "id": row.id, "source": "analyst-verdict"}


@router.get("/ml/feedback/stats")
async def feedback_stats(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Feedback inventory: counts by source and label (viewer+)."""
    tenant_id = current_tenant_id.get() or 1
    stmt = (
        select(TrainingFeedback.source, TrainingFeedback.label,
               func.count(TrainingFeedback.id))
        .where(TrainingFeedback.tenant_id == tenant_id)
        .group_by(TrainingFeedback.source, TrainingFeedback.label)
    )
    rows = (await db.execute(stmt)).all()
    by_source: dict[str, dict] = {}
    total = 0
    for source, label, count in rows:
        by_source.setdefault(source, {"attack": 0, "benign": 0})
        by_source[source][label] = int(count)
        total += int(count)
    return {"total": total, "by_source": by_source}
