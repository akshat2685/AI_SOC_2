from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any

from app.infrastructure.database import get_db
from app.domain.models import Incident, Alert, RoleEnum, StatusEnum, SeverityEnum
from app.core.auth import current_user_id, current_tenant_id
from app.api.deps import require_roles_dual, TokenData

router = APIRouter()

# Any authenticated user (viewer+) may read incidents; mutating actions
# (status updates, verdicts) require analyst or admin.
READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]


def _incident_to_dict(inc: Incident) -> Dict[str, Any]:
    return {
        "id": inc.id,
        "title": inc.title,
        "severity": inc.severity.value if inc.severity else "UNKNOWN",
        "status": inc.status.value if inc.status else "UNKNOWN",
        "timestamp": inc.created_at.isoformat() if inc.created_at else None,
        "llm_summary": inc.description,
        "verdict": inc.verdict or "UNKNOWN",
        "analyst_notes": inc.analyst_notes or "",
    }


@router.get("")
async def get_incidents(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.tenant_id == tenant_id))
    incidents = result.scalars().all()
    return [_incident_to_dict(inc) for inc in incidents]


@router.get("/{id}/details")
async def get_incident_details(
    id: int,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.id == id, Incident.tenant_id == tenant_id))
    incident = result.scalars().first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    alerts_result = await db.execute(select(Alert).where(Alert.incident_id == id))
    alerts = alerts_result.scalars().all()

    return {
        "id": incident.id,
        "title": incident.title,
        "severity": incident.severity.value if incident.severity else "UNKNOWN",
        "status": incident.status.value if incident.status else "UNKNOWN",
        "verdict": incident.verdict or "UNKNOWN",
        "analyst_notes": incident.analyst_notes or "",
        "logs": [],
        "alerts": [{"id": a.id, "title": a.rule_name, "severity": "HIGH", "timestamp": a.timestamp.isoformat()} for a in alerts],
        "related_logs": [],
        "iocs": [],
        "actions": []
    }


@router.put("/{id}")
async def update_incident(
    id: int,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.id == id, Incident.tenant_id == tenant_id))
    incident = result.scalars().first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if "status" in data and data["status"]:
        try:
            incident.status = StatusEnum(str(data["status"]).upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{data['status']}': must be one of OPEN, IN_PROGRESS, RESOLVED, CLOSED",
            )
    if "verdict" in data and data["verdict"] is not None:
        incident.verdict = str(data["verdict"]).upper()[:50]
    if "analyst_notes" in data and data["analyst_notes"] is not None:
        incident.analyst_notes = str(data["analyst_notes"])

    await db.commit()
    await db.refresh(incident)
    # Self-learning: a resolved incident with a verdict becomes labeled
    # training data. TP -> attack samples, FP -> benign samples. Never raises.
    try:
        status_val = str(incident.status.value if incident.status else "")
        verdict_val = str(incident.verdict or "").upper()
        if status_val in ("RESOLVED", "CLOSED") and verdict_val in ("TRUE_POSITIVE", "FALSE_POSITIVE"):
            from app.ml.feedback import record_incident_feedback as _record_fb

            await _record_fb(db, id, verdict_val)
            await db.commit()
    except Exception:
        from app.core.logger import logger as _logger

        _logger.error("incident_feedback_failed", incident_id=id, exc_info=True)
    return {"status": "success", "incident": _incident_to_dict(incident)}


@router.post("/{id}/verdict")
async def set_verdict(
    id: int,
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.id == id, Incident.tenant_id == tenant_id))
    incident = result.scalars().first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    verdict = str(data.get("verdict", "UNKNOWN")).upper()[:50]
    incident.verdict = verdict
    if data.get("notes"):
        incident.analyst_notes = str(data["notes"])
    await db.commit()
    await db.refresh(incident)
    return {"status": "success", "id": incident.id, "verdict": incident.verdict}


@router.get("/{id}/predict-risk")
async def predict_risk(
    id: int,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.id == id, Incident.tenant_id == tenant_id))
    incident = result.scalars().first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    alerts_result = await db.execute(select(Alert).where(Alert.incident_id == id))
    alert_count = len(alerts_result.scalars().all())

    # Heuristic score: severity base + linked-alert pressure, capped at 99.
    # Labeled honestly: no ML model is wired in this build.
    base = {
        SeverityEnum.CRITICAL: 85,
        SeverityEnum.HIGH: 70,
        SeverityEnum.MEDIUM: 50,
        SeverityEnum.LOW: 30,
    }.get(incident.severity, 50)
    risk_score = min(99, base + min(alert_count * 3, 14))
    risk_level = "Critical" if risk_score >= 85 else "High" if risk_score >= 65 else "Medium" if risk_score >= 40 else "Low"

    # ML block: score incident-derived features with the synthetic-trained models.
    # Time/asset come from the incident; telemetry counters are defaulted to
    # benign medians (labeled as such) until real telemetry is wired in.
    ml_block = None
    try:
        from app.ml import inference as ml_inf
        if ml_inf.models_available():
            created = incident.created_at
            hour = created.hour if created else 12
            feats = {
                "hour_of_day": hour,
                "day_of_week": created.weekday() if created else 2,
                "off_hours": 1 if (hour < 8 or hour >= 20) else 0,
                "failed_logins_1h": 1,
                "unique_dst_ips_1h": 8,
                "bytes_out_mb_1h": 12.0,
                "new_process_rarity": 0.1,
                "dns_query_entropy": 0.3,
                "alert_count_1h": alert_count,
                "src_asset_type": "workstation",
            }
            ml_block = {
                "triage": ml_inf.predict_triage(feats),
                "anomaly": ml_inf.predict_anomaly(feats),
                "model_version": ml_inf.MODEL_VERSION,
                "trained_on": ml_inf.TRAINED_ON,
                "features": "partial — time/asset from incident, telemetry defaulted to benign medians",
                "warning": ml_inf.WARNING,
            }
    except Exception:
        ml_block = None

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "likelihood": f"{risk_score}%",
        "reasoning": (
            f"Heuristic score from incident severity "
            f"({incident.severity.value if incident.severity else 'UNKNOWN'}) and "
            f"{alert_count} linked alert(s). See the 'ml' block for model scores "
            f"(synthetic-trained v1) when available."
        ),
        "mitigation": "Isolate affected hosts, rotate credentials, and review linked alerts.",
        "model": "heuristic-v1",
        "ml": ml_block,
    }


@router.get("/{id}/graph")
async def get_graph(
    id: int,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.id == id, Incident.tenant_id == tenant_id))
    incident = result.scalars().first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    alerts_result = await db.execute(select(Alert).where(Alert.incident_id == id))
    alerts = alerts_result.scalars().all()

    nodes = [{"id": f"incident-{incident.id}", "label": incident.title, "type": "incident"}]
    edges = []
    for a in alerts:
        nodes.append({"id": f"alert-{a.id}", "label": a.rule_name, "type": "alert"})
        edges.append({"source": f"alert-{a.id}", "target": f"incident-{incident.id}", "type": "TRIGGERED"})

    return {"nodes": nodes, "edges": edges}


@router.get("/{id}/recommended-triage")
async def recommended_triage(
    id: int,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    tenant_id = current_tenant_id.get() or 1
    result = await db.execute(select(Incident).where(Incident.id == id, Incident.tenant_id == tenant_id))
    incident = result.scalars().first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    sev = incident.severity.value if incident.severity else "MEDIUM"
    recommendations = {
        "CRITICAL": "Isolate the affected endpoints immediately, rotate credentials, block attacker infrastructure at the firewall, and escalate to the incident commander.",
        "HIGH": "Isolate the endpoint, rotate credentials for affected accounts, and contain lateral movement before deeper forensics.",
        "MEDIUM": "Review the linked alerts, verify whether the activity is benign, and monitor the host for 24 hours.",
        "LOW": "Log the finding, verify with the asset owner, and close if benign.",
    }
    return {
        "recommendation": recommendations.get(sev, recommendations["MEDIUM"]),
        "severity": sev,
    }
