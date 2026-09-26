"""ML inference endpoints: triage classifier + anomaly (0-day) detector.

Models are synthetic-trained v1 (see app/ml). Every response carries the
model version, training provenance, and the retrain warning.
"""

import json
import os

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_roles_dual
from app.domain.models import RoleEnum
from app.ml import inference as ml

router = APIRouter()
READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]


def _report() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ml", "artifacts", "training_report.json")
    path = os.path.normpath(path)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


@router.get("/ml/models")
async def ml_models(_auth=Depends(require_roles_dual(READ_ROLES))):
    """Model inventory: availability, version, training metrics, provenance."""
    return {
        "available": ml.models_available(),
        "model_version": ml.MODEL_VERSION,
        "trained_on": ml.TRAINED_ON,
        "warning": ml.WARNING,
        "zero_day_note": ml.ZERO_DAY_NOTE,
        "training_report": _report(),
    }


@router.post("/ml/analyze")
async def ml_analyze(features: dict, _auth=Depends(require_roles_dual(READ_ROLES))):
    """Score one telemetry feature vector with both models.

    Expected features (missing numerics default to 0):
    hour_of_day, day_of_week, off_hours, failed_logins_1h, unique_dst_ips_1h,
    bytes_out_mb_1h, new_process_rarity, dns_query_entropy, alert_count_1h,
    src_asset_type ("workstation" | "server" | "database").
    """
    if not ml.models_available():
        raise HTTPException(status_code=503, detail="ML models are not loaded on this backend.")
    if not isinstance(features, dict):
        raise HTTPException(status_code=400, detail="Provide a JSON object of features.")
    return {
        "triage": ml.predict_triage(features),
        "anomaly": ml.predict_anomaly(features),
        "model_version": ml.MODEL_VERSION,
        "trained_on": ml.TRAINED_ON,
        "warning": ml.WARNING,
        "zero_day_note": ml.ZERO_DAY_NOTE,
    }
