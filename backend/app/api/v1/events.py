"""Phase 1 telemetry: normalized security-event ingestion + query.

Agents authenticate with a tenant API key (no JWT). The dual-auth
middleware resolves the tenant from the API key into `current_tenant_id`,
so `require_roles_dual` admits key-authenticated agents while JWT users
still get role enforcement.

Contract (the sensor team codes to this exact shape):
  POST /ingest  {device_id, events: [{event_type, observed_at, severity_hint,
                 process|network|file|auth|dns, raw}]}
  GET  /        ?device_id=&event_type=&since=&severity_hint=&limit=&offset=
  GET  /stats/summary

Honesty rules: invalid events are reported in `rejected` with a per-item
reason — never silently dropped. Nothing is enriched; the payload stored
is exactly what the sensor sent.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles_dual
from app.core.auth import current_tenant_id
from app.domain.models import (
    EndpointAgent,
    EventType,
    RoleEnum,
    SecurityEvent,
    SeverityHint,
)
from app.infrastructure.database import get_db

router = APIRouter()
logger = structlog.get_logger(__name__)

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]

MAX_BATCH = 1000
MAX_LIMIT = 1000
DEFAULT_LIMIT = 100

# The typed section key that must be present for each event_type.
REQUIRED_SECTION = {
    EventType.PROCESS: "process",
    EventType.NETWORK: "network",
    EventType.FILE: "file",
    EventType.AUTH: "auth",
    EventType.DNS: "dns",
}


def _tenant_id() -> int:
    return current_tenant_id.get() or 1


def _parse_ts(value: Any) -> datetime:
    """Parse an ISO8601 timestamp; naive values are assumed UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("observed_at must be a non-empty ISO8601 string")
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(s)
    except ValueError:
        raise ValueError(f"observed_at is not parseable as ISO8601: {value!r}")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _validate_event(index: int, event: Any) -> SecurityEvent:
    """Validate one raw event dict; raise ValueError with a human reason."""
    if not isinstance(event, dict):
        raise ValueError("event must be a JSON object")
    raw_type = event.get("event_type")
    try:
        event_type = EventType(str(raw_type).strip().lower()) if raw_type else None
    except ValueError:
        event_type = None
    if event_type is None:
        valid = sorted(e.value for e in EventType)
        raise ValueError(f"invalid event_type {raw_type!r}; must be one of {valid}")

    observed_at = _parse_ts(event.get("observed_at"))

    raw_sev = event.get("severity_hint", SeverityHint.INFO.value)
    try:
        severity_hint = SeverityHint(str(raw_sev).strip().lower())
    except ValueError:
        valid = sorted(s.value for s in SeverityHint)
        raise ValueError(f"invalid severity_hint {raw_sev!r}; must be one of {valid}")

    section_key = REQUIRED_SECTION[event_type]
    section = event.get(section_key)
    if not isinstance(section, dict):
        raise ValueError(f"event_type '{event_type.value}' requires a '{section_key}' object section")

    raw = event.get("raw")
    if raw is not None and not isinstance(raw, dict):
        raise ValueError("'raw' must be a JSON object when present")

    return SecurityEvent(
        tenant_id=_tenant_id(),
        device_id="",  # filled by the caller from the batch device_id
        event_type=event_type,
        observed_at=observed_at,
        severity_hint=severity_hint,
        payload=section,
        raw=raw or {},
    )


def _event_to_dict(e: SecurityEvent) -> Dict[str, Any]:
    et = e.event_type.value if isinstance(e.event_type, EventType) else e.event_type
    sev = e.severity_hint.value if isinstance(e.severity_hint, SeverityHint) else e.severity_hint
    return {
        "id": str(e.id),
        "tenant_id": e.tenant_id,
        "device_id": e.device_id,
        "event_type": et,
        "observed_at": e.observed_at.isoformat() if e.observed_at else None,
        "severity_hint": sev,
        "payload": e.payload,
        "raw": e.raw,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


@router.post("/ingest")
async def ingest_events(
    body: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
):
    """Ingest a batch of normalized events from an agent.

    Auth: tenant API key (agents have no JWT) or JWT with analyst+.
    The device must exist AND belong to the caller's tenant, else 404 —
    cross-tenant device_ids are indistinguishable from unknown ones.
    """
    tenant_id = _tenant_id()
    device_id = str(body.get("device_id") or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="Provide 'device_id'.")
    events = body.get("events")
    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="'events' must be a JSON array.")
    if len(events) > MAX_BATCH:
        raise HTTPException(
            status_code=413,
            detail=f"Batch too large: {len(events)} events; max is {MAX_BATCH}. Split the batch.",
        )

    result = await db.execute(
        select(EndpointAgent).where(
            EndpointAgent.device_id == device_id, EndpointAgent.tenant_id == tenant_id
        )
    )
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    accepted: List[SecurityEvent] = []
    errors: List[Dict[str, Any]] = []
    for i, raw_event in enumerate(events):
        try:
            ev = _validate_event(i, raw_event)
            ev.device_id = device_id
            accepted.append(ev)
        except ValueError as exc:
            errors.append({"index": i, "reason": str(exc)})

    if accepted:
        db.add_all(accepted)
    now = datetime.now(timezone.utc)
    agent.last_seen_at = now
    await db.commit()

    logger.info(
        "events_ingested",
        device_id=device_id,
        accepted=len(accepted),
        rejected=len(errors),
    )
    return {
        "device_id": device_id,
        "accepted": len(accepted),
        "rejected": len(errors),
        "errors": errors,
        "note": "Rejected events are listed per-index with reasons; nothing was silently dropped.",
    }


# NOTE: literal routes must be registered before any parameterized ones.
@router.get("/stats/summary")
async def events_summary(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Counts by event_type for the tenant in the last 24h, plus the
    number of distinct devices that reported in that window. All from
    real rows; zero fabrication."""
    tenant_id = _tenant_id()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    by_type_rows = (
        await db.execute(
            select(SecurityEvent.event_type, func.count(SecurityEvent.id))
            .where(SecurityEvent.tenant_id == tenant_id, SecurityEvent.observed_at >= cutoff)
            .group_by(SecurityEvent.event_type)
        )
    ).all()
    by_event_type = {
        (et.value if isinstance(et, EventType) else str(et)): n for et, n in by_type_rows
    }

    devices_reporting = (
        await db.execute(
            select(func.count(func.distinct(SecurityEvent.device_id))).where(
                SecurityEvent.tenant_id == tenant_id, SecurityEvent.observed_at >= cutoff
            )
        )
    ).scalar() or 0

    total_24h = sum(by_event_type.values())
    return {
        "window_hours": 24,
        "total_events_24h": total_24h,
        "by_event_type": by_event_type,
        "devices_reporting_24h": devices_reporting,
        "note": "Counts are from stored security_events rows for this tenant; no estimates.",
    }


@router.get("")
async def query_events(
    device_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    severity_hint: Optional[str] = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(READ_ROLES)),
):
    """Query stored events, newest first. Always tenant-scoped."""
    tenant_id = _tenant_id()
    stmt = select(SecurityEvent).where(SecurityEvent.tenant_id == tenant_id)

    if device_id:
        stmt = stmt.where(SecurityEvent.device_id == device_id.strip())
    if event_type:
        try:
            et = EventType(event_type.strip().lower())
        except ValueError:
            valid = sorted(e.value for e in EventType)
            raise HTTPException(status_code=400, detail=f"Invalid event_type. Valid: {valid}")
        stmt = stmt.where(SecurityEvent.event_type == et)
    if severity_hint:
        try:
            sev = SeverityHint(severity_hint.strip().lower())
        except ValueError:
            valid = sorted(s.value for s in SeverityHint)
            raise HTTPException(status_code=400, detail=f"Invalid severity_hint. Valid: {valid}")
        stmt = stmt.where(SecurityEvent.severity_hint == sev)
    if since:
        try:
            since_ts = _parse_ts(since)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        stmt = stmt.where(SecurityEvent.observed_at >= since_ts)

    total = (
        await db.execute(
            select(func.count()).select_from(stmt.subquery())
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            stmt.order_by(SecurityEvent.observed_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return {
        "events": [_event_to_dict(e) for e in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
