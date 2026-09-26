"""Alert -> incident correlation (Phase 2).

Groups new alerts by device: each device's alerts attach to an already-open
incident for that device (created in the trailing 24h), or a new incident
is opened. This is the automatic incident-creation path — analysts can also
promote a single alert manually via POST /alerts/{id}/promote.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Alert, Incident, SeverityEnum, StatusEnum

CORRELATION_WINDOW = timedelta(hours=24)

_SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _to_severity_enum(sev: str | None) -> SeverityEnum:
    return SeverityEnum.__members__.get((sev or "MEDIUM").upper(), SeverityEnum.MEDIUM)


def _max_severity(alerts: list[Alert]) -> str:
    best = "LOW"
    for a in alerts:
        s = (a.severity or "LOW").upper()
        if _SEVERITY_ORDER.get(s, 0) > _SEVERITY_ORDER.get(best, 0):
            best = s
    return best


async def _open_incident_for_device(
    db: AsyncSession, tenant_id: int, device_id: str, since: datetime
) -> Incident | None:
    stmt = (
        select(Incident)
        .join(Alert, Alert.incident_id == Incident.id)
        .where(
            Incident.tenant_id == tenant_id,
            Incident.status == StatusEnum.OPEN,
            Alert.device_id == device_id,
            Incident.created_at >= since,
        )
        .order_by(Incident.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def correlate_new_alerts(
    db: AsyncSession,
    tenant_id: int,
    alerts: list[Alert],
    hostnames: dict[str, str] | None = None,
) -> dict:
    """Attach alerts to incidents. Returns counts."""
    hostnames = hostnames or {}
    now = datetime.now(timezone.utc)
    window_start = now - CORRELATION_WINDOW

    by_device: dict[str, list[Alert]] = defaultdict(list)
    for a in alerts:
        by_device[a.device_id or "unknown"].append(a)

    created = 0
    attached = 0
    for device_id, group in by_device.items():
        incident = await _open_incident_for_device(db, tenant_id, device_id, window_start)
        if incident is None:
            top = max(group, key=lambda a: _SEVERITY_ORDER.get((a.severity or "LOW").upper(), 0))
            label = hostnames.get(device_id, device_id)
            rule_names = sorted({a.rule_name for a in group})
            incident = Incident(
                tenant_id=tenant_id,
                title=f"{top.rule_name} on {label}",
                description=(
                    f"Auto-correlated by the detection engine from {len(group)} alert(s) "
                    f"on device {label} ({device_id}). Rules fired: {', '.join(rule_names)}."
                ),
                severity=_to_severity_enum(_max_severity(group)),
                status=StatusEnum.OPEN,
                verdict="UNKNOWN",
            )
            db.add(incident)
            await db.flush()
            created += 1
        for a in group:
            a.incident_id = incident.id
            attached += 1

    await db.flush()
    return {"incidents_created": created, "incidents_attached": attached}


async def promote_alert(db: AsyncSession, tenant_id: int, alert_id: int) -> Incident:
    """Manually promote one alert to its own incident (analyst action)."""
    alert = await db.get(Alert, alert_id)
    if alert is None or alert.tenant_id != tenant_id:
        raise ValueError("alert not found")
    if alert.incident_id is not None:
        existing = await db.get(Incident, alert.incident_id)
        if existing is not None:
            return existing
    incident = Incident(
        tenant_id=tenant_id,
        title=f"{alert.rule_name} (promoted alert #{alert.id})",
        description=(
            f"Manually promoted from alert #{alert.id} by an analyst.\n\n"
            f"{alert.description or ''}"
        ),
        severity=_to_severity_enum(alert.severity),
        status=StatusEnum.OPEN,
        verdict="UNKNOWN",
    )
    db.add(incident)
    await db.flush()
    alert.incident_id = incident.id
    await db.flush()
    return incident
