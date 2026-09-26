"""Collect labeled training rows for the self-learning retrain loop.

Two writers:
  - record_incident_feedback: an analyst resolves an incident with a
    true/false-positive verdict; the incident's alerts are replayed into
    device-hour feature vectors (the same 15 columns the models train on)
    and stored as labeled rows.
  - record_sparring_rows: the digital-twin sparring simulator hands us
    (feature_vector, technique_id, label) rows directly.

Nothing here trains or touches artifacts -- the standalone
retrain_with_feedback.py does that under a regression gate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.detection.features import build_hourly_features
from app.domain.models import (Alert, EventType, Incident, SecurityEvent,
                               TrainingFeedback)
from app.ml.threat_data import FEATURE_COLUMNS, SEVERITY_BY_TACTIC

# Best-effort mapping from rules-v1 rule_ids to the ATT&CK technique they most
# closely approximate. Nullable by design: a wrong technique label is worse
# than none, so unmapped rules stay None.
RULE_TO_TECHNIQUE: dict[str, tuple[str, str]] = {
    "suspicious-cmdline": ("T1059.001", "execution"),
    "persistence-change": ("T1547.001", "persistence"),
    "rare-outbound-port": ("T1071.001", "command-and-control"),
}

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _event_to_dict(e: SecurityEvent) -> dict:
    """Same shape detection/features.py expects (mirrors engine._event_to_dict)."""
    et = e.event_type.value if isinstance(e.event_type, EventType) else e.event_type
    return {
        "id": str(e.id),
        "device_id": e.device_id,
        "event_type": et,
        "observed_at": e.observed_at,
        "severity_hint": e.severity_hint,
        "payload": e.payload or {},
    }


async def _known_process_names(db: AsyncSession, tenant_id: int,
                               device_id: str) -> set[str]:
    """Process names seen for this device in the trailing 30 days."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    stmt = (
        select(SecurityEvent.payload["name"].astext)
        .where(
            SecurityEvent.tenant_id == tenant_id,
            SecurityEvent.device_id == device_id,
            SecurityEvent.event_type == EventType.PROCESS,
            SecurityEvent.observed_at >= since,
        )
        .distinct()
    )
    rows = (await db.execute(stmt)).all()
    return {str(r[0]).lower() for r in rows if r[0]}


def _expand_vector(feats: dict) -> dict:
    """Build the 15 FEATURE_COLUMNS values in exact order from a feature dict.

    Accepts either the 13-key build_hourly_features output (with
    src_asset_type) or a dict that already carries asset_* one-hots.
    Missing numerics default to 0 -- never invented, just zero-filled.
    """
    asset_type = str(feats.get("src_asset_type", "workstation")).lower()
    out: dict[str, float] = {}
    for col in FEATURE_COLUMNS:
        if col.startswith("asset_"):
            if col in feats:
                out[col] = float(feats[col] or 0)
            else:
                out[col] = 1.0 if col == f"asset_{asset_type}" else 0.0
        else:
            try:
                out[col] = float(feats.get(col, 0) or 0)
            except (TypeError, ValueError):
                out[col] = 0.0
    return out


async def record_incident_feedback(
    db: AsyncSession, incident_id: int, verdict: str
) -> dict:
    """Store one labeled row per alert device-hour after an analyst verdict.

    verdict: "true_positive" | "false_positive" (case-insensitive).
    Idempotent per incident: re-resolving the same incident writes nothing.
    """
    v = verdict.strip().lower()
    if v not in ("true_positive", "false_positive"):
        raise ValueError(f"verdict must be true_positive|false_positive, got {verdict!r}")
    is_attack = v == "true_positive"

    incident = (await db.execute(
        select(Incident).where(Incident.id == incident_id))).scalars().first()
    if not incident:
        raise ValueError(f"incident {incident_id} not found")
    tenant_id = incident.tenant_id

    # Idempotency: an incident contributes its telemetry exactly once.
    already = (await db.execute(
        select(TrainingFeedback.id)
        .where(TrainingFeedback.incident_id == incident_id)
        .limit(1))).first()
    if already:
        return {"recorded": 0, "incident_id": incident_id,
                "reason": "feedback already recorded for this incident"}

    alerts = (await db.execute(
        select(Alert).where(Alert.incident_id == incident_id))).scalars().all()
    if not alerts:
        return {"recorded": 0, "incident_id": incident_id,
                "reason": "incident has no alerts"}

    recorded = 0
    seen_buckets: set[tuple[str, str]] = set()
    for alert in alerts:
        device_id = alert.device_id
        if not device_id or not alert.timestamp:
            continue
        ts = alert.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hour_start = ts.replace(minute=0, second=0, microsecond=0)
        key = (device_id, hour_start.isoformat())
        if key in seen_buckets:
            continue
        seen_buckets.add(key)

        stmt = (
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == tenant_id,
                SecurityEvent.device_id == device_id,
                SecurityEvent.observed_at >= hour_start,
                SecurityEvent.observed_at < hour_start + timedelta(hours=1),
            )
            .order_by(SecurityEvent.observed_at.asc())
        )
        events = [_event_to_dict(e) for e in (await db.execute(stmt)).scalars().all()]
        if not events:
            continue

        known = await _known_process_names(db, tenant_id, device_id)
        feats = build_hourly_features(events, hour_start, known, alert_count_1h=0)
        vector = _expand_vector(feats)

        technique_id, tactic = None, None
        if is_attack and alert.rule_id in RULE_TO_TECHNIQUE:
            technique_id, tactic = RULE_TO_TECHNIQUE[alert.rule_id]
        sev = getattr(incident, "severity", None) or alert.severity
        severity = str(getattr(sev, "value", sev) or "").upper()
        if severity not in SEVERITIES:
            severity = "HIGH" if is_attack else "LOW"

        db.add(TrainingFeedback(
            tenant_id=tenant_id,
            incident_id=incident_id,
            device_id=device_id,
            feature_vector=vector,
            label="attack" if is_attack else "benign",
            technique_id=technique_id,
            tactic=tactic,
            severity=severity,
            source="analyst-verdict",
        ))
        recorded += 1

    await db.commit()
    return {"recorded": recorded, "incident_id": incident_id,
            "label": "attack" if is_attack else "benign"}


async def record_sparring_rows(
    db: AsyncSession, tenant_id: int, rows: list[dict]
) -> dict:
    """Store rows from the digital-twin sparring simulator.

    Each row: {"feature_vector": {15 features}, "technique_id": str|None,
               "tactic": str|None, "label": "attack"|"benign",
               "severity": str|None, "device_id": str|None}
    """
    recorded = 0
    for r in rows:
        label = str(r.get("label", "")).lower()
        if label not in ("attack", "benign"):
            raise ValueError(f"sparring row label must be attack|benign, got {r.get('label')!r}")
        tactic = r.get("tactic")
        severity = str(r.get("severity") or "").upper()
        if severity not in SEVERITIES:
            severity = (SEVERITY_BY_TACTIC.get(str(tactic), "MEDIUM")
                        if label == "attack" else "LOW")
        db.add(TrainingFeedback(
            tenant_id=tenant_id,
            incident_id=None,
            device_id=r.get("device_id"),
            feature_vector=_expand_vector(r.get("feature_vector") or {}),
            label=label,
            technique_id=r.get("technique_id"),
            tactic=tactic,
            severity=severity,
            source="sparring",
        ))
        recorded += 1
    await db.commit()
    return {"recorded": recorded, "source": "sparring"}


def feedback_to_dataframe(rows: list[TrainingFeedback]):
    """Convert stored rows to a DataFrame shaped like threat_data.generate().

    Label columns: is_attack, tactic, technique_id, severity, provenance,
    archetype -- so the retrain script can concat directly.
    """
    import pandas as pd

    records: list[dict[str, Any]] = []
    for r in rows:
        vec = r.feature_vector or {}
        rec = {c: float(vec.get(c, 0) or 0) for c in FEATURE_COLUMNS}
        rec["is_attack"] = 1 if r.label == "attack" else 0
        rec["tactic"] = r.tactic or ("attack" if r.label == "attack" else "benign")
        rec["technique_id"] = r.technique_id or "feedback"
        rec["severity"] = r.severity if r.severity in SEVERITIES else "MEDIUM"
        rec["provenance"] = "feedback"
        rec["archetype"] = "feedback"
        records.append(rec)
    return pd.DataFrame(records, columns=FEATURE_COLUMNS + [
        "is_attack", "tactic", "technique_id", "severity", "provenance",
        "archetype"])
