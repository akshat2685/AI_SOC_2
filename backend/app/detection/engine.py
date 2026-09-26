"""Phase 2 detection engine: rules + anomaly scoring over ingested telemetry.

scan_tenant() is the single entry point. It:
  1. resumes from the per-tenant watermark (never double-scans),
  2. runs rules-v1 over new events (see detection/rules.py),
  3. scores per-device hourly aggregates with the IsolationForest 0-day
     model when it is available (see detection/features.py),
  4. dedups findings against recent alerts,
  5. persists Alert rows with real severity / confidence / evidence,
  6. correlates new alerts into incidents (see detection/correlate.py),
  7. advances the watermark.

All DB access lives here; rules.py and features.py stay pure and testable.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import (
    Alert,
    DetectionWatermark,
    EndpointAgent,
    EventType,
    SecurityEvent,
    SeverityEnum,
    StatusEnum,
)
from app.detection import rules as rules_mod
from app.detection import features as features_mod
from app.detection.correlate import correlate_new_alerts
from app.ml import inference as ml_inference

logger = logging.getLogger(__name__)

ENGINE_VERSION = "detection-v1"
FIRST_SCAN_LOOKBACK = timedelta(hours=24)
DEDUP_WINDOW = timedelta(hours=6)
MAX_EVENTS_PER_SCAN = 5000
HISTORY_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _get_watermark(db: AsyncSession, tenant_id: int) -> DetectionWatermark:
    wm = await db.get(DetectionWatermark, tenant_id)
    if wm is None:
        wm = DetectionWatermark(tenant_id=tenant_id)
        db.add(wm)
        await db.flush()
    return wm


async def _known_hashes(db: AsyncSession, tenant_id: int, since: datetime) -> set[str]:
    """Distinct process binary hashes seen in the trailing history window."""
    try:
        stmt = (
            select(SecurityEvent.payload["hash_sha256"].astext)
            .where(
                SecurityEvent.tenant_id == tenant_id,
                SecurityEvent.event_type == EventType.PROCESS,
                SecurityEvent.observed_at >= since,
            )
            .distinct()
        )
        rows = (await db.execute(stmt)).scalars().all()
        return {r for r in rows if r}
    except Exception as exc:  # JSON operators differ per backend; degrade, don't die
        logger.warning("known_hashes query failed, continuing without: %s", exc)
        return set()


async def _known_process_names(db: AsyncSession, tenant_id: int, since: datetime) -> dict[str, set[str]]:
    """device_id -> set of lowercased process names seen in the history window."""
    try:
        stmt = select(
            SecurityEvent.device_id,
            SecurityEvent.payload["name"].astext,
        ).where(
            SecurityEvent.tenant_id == tenant_id,
            SecurityEvent.event_type == EventType.PROCESS,
            SecurityEvent.observed_at >= since,
        )
        rows = (await db.execute(stmt)).all()
        out: dict[str, set[str]] = defaultdict(set)
        for device_id, name in rows:
            if name:
                out[device_id].add(name.lower())
        return out
    except Exception as exc:
        logger.warning("known_process_names query failed, continuing without: %s", exc)
        return {}


async def _recent_fingerprints(db: AsyncSession, tenant_id: int, since: datetime) -> set[str]:
    """Fingerprints of alerts already raised in the dedup window."""
    stmt = select(Alert.evidence).where(
        Alert.tenant_id == tenant_id,
        Alert.timestamp >= since,
        Alert.rule_id.isnot(None),
    )
    rows = (await db.execute(stmt)).scalars().all()
    fps = set()
    for ev in rows:
        if isinstance(ev, dict) and ev.get("fingerprint"):
            fps.add(ev["fingerprint"])
    return fps


async def _hostnames(db: AsyncSession, tenant_id: int, device_ids: set[str]) -> dict[str, str]:
    if not device_ids:
        return {}
    stmt = select(EndpointAgent.device_id, EndpointAgent.hostname).where(
        EndpointAgent.tenant_id == tenant_id,
        EndpointAgent.device_id.in_(device_ids),
    )
    return {d: h for d, h in (await db.execute(stmt)).all()}


def _event_to_dict(e: SecurityEvent) -> dict:
    et = e.event_type.value if isinstance(e.event_type, EventType) else e.event_type
    return {
        "id": str(e.id),
        "device_id": e.device_id,
        "event_type": et,
        "observed_at": e.observed_at,
        "severity_hint": e.severity_hint,
        "payload": e.payload or {},
    }


async def scan_tenant(db: AsyncSession, tenant_id: int, lookback_hours: int | None = None) -> dict:
    """Run one detection pass for a tenant. Returns a summary dict.

    lookback_hours: when set, ignore the watermark and scan this many
    trailing hours (dedup window stretches to match, so a deliberate
    rescan does not duplicate alerts).
    """
    now = _utcnow()
    wm = await _get_watermark(db, tenant_id)
    if lookback_hours is not None:
        if not (1 <= lookback_hours <= 24 * 30):
            raise ValueError("lookback_hours must be between 1 and 720")
        since = now - timedelta(hours=lookback_hours)
        dedup_window = max(DEDUP_WINDOW, timedelta(hours=lookback_hours))
    else:
        since = wm.last_scan_at or (now - FIRST_SCAN_LOOKBACK)
        dedup_window = DEDUP_WINDOW

    stmt = (
        select(SecurityEvent)
        .where(SecurityEvent.tenant_id == tenant_id, SecurityEvent.observed_at > since)
        .order_by(SecurityEvent.observed_at.asc())
        .limit(MAX_EVENTS_PER_SCAN)
    )
    events = list((await db.execute(stmt)).scalars().all())
    event_dicts = [_event_to_dict(e) for e in events]

    history_since = now - timedelta(days=HISTORY_DAYS)
    known_hashes = await _known_hashes(db, tenant_id, history_since)
    known_names = await _known_process_names(db, tenant_id, history_since)
    seen_fps = await _recent_fingerprints(db, tenant_id, now - dedup_window)

    rules_fired: dict[str, int] = defaultdict(int)
    new_alerts: list[Alert] = []
    max_observed = since

    # --- rule pass ---
    for ev in event_dicts:
        if ev["observed_at"] and ev["observed_at"] > max_observed:
            max_observed = ev["observed_at"]
        for finding in rules_mod.match_rules(ev, known_hashes=known_hashes):
            fp = finding["fingerprint"]
            if fp in seen_fps:
                continue
            seen_fps.add(fp)
            rules_fired[finding["rule_id"]] += 1
            alert = Alert(
                tenant_id=tenant_id,
                source="detection-engine",
                rule_name=finding["rule_name"],
                description=finding["description"],
                severity=finding["severity"],
                confidence=finding["confidence"],
                device_id=ev["device_id"],
                rule_id=finding["rule_id"],
                evidence={
                    **finding["evidence"],
                    "fingerprint": fp,
                    "detector": rules_mod.RULES_VERSION,
                    "engine": ENGINE_VERSION,
                    "event_id": ev["id"],
                },
            )
            db.add(alert)
            new_alerts.append(alert)

    # --- anomaly pass (per device-hour aggregates) ---
    anomaly_fired = 0
    if ml_inference.models_available():
        buckets = features_mod.bucket_by_device_hour(event_dicts)
        # alert counts per (device, hour) from the rule pass, for the feature
        rule_alert_hours: dict[tuple[str, str], int] = defaultdict(int)
        for a in new_alerts:
            ev_id = (a.evidence or {}).get("event_id")
            # cheap mapping: recompute hour key from the alert's timestamp
            ts = a.timestamp or now
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            rule_alert_hours[(a.device_id or "unknown", ts.strftime("%Y-%m-%dT%H"))] += 1

        for (device_id, hour_key), bucket in buckets.items():
            if len(bucket) < features_mod.ANOMALY_MIN_EVENTS:
                continue
            window_start = datetime.strptime(hour_key, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
            feats = features_mod.build_hourly_features(
                bucket, window_start,
                known_process_names=known_names.get(device_id, set()),
                alert_count_1h=rule_alert_hours.get((device_id, hour_key), 0),
            )
            try:
                result = ml_inference.predict_anomaly(feats)
            except Exception as exc:
                logger.warning("anomaly inference failed for %s: %s", device_id, exc)
                continue
            if not result or not result.get("is_anomaly"):
                continue
            fp = f"ml-anomaly:{device_id}:{hour_key}"
            if fp in seen_fps:
                continue
            seen_fps.add(fp)
            anomaly_fired += 1
            score = result["anomaly_score"]
            alert = Alert(
                tenant_id=tenant_id,
                source="detection-engine",
                rule_name="Behavioral anomaly (0-day signal)",
                description=(
                    f"Device {device_id} showed anomalous behavior in hour {hour_key} UTC "
                    f"(anomaly score {score:.2f}). The IsolationForest model was fit on benign-only "
                    f"traffic and flags behavioral deviations, not signatures — "
                    f"{len(bucket)} events in the window."
                ),
                severity="MEDIUM",
                confidence=int(score * 100),
                device_id=device_id,
                rule_id="ml-anomaly",
                evidence={
                    "fingerprint": fp,
                    "detector": "ml-anomaly-v1",
                    "model_version": ml_inference.MODEL_VERSION,
                    "model_trained_on": ml_inference.TRAINED_ON,
                    "anomaly_score": score,
                    "features": feats,
                    "engine": ENGINE_VERSION,
                },
            )
            db.add(alert)
            new_alerts.append(alert)
    else:
        logger.info("ml models unavailable; anomaly pass skipped (rules still ran)")

    await db.flush()  # assign ids before correlation

    # --- correlate into incidents ---
    hostnames = await _hostnames(db, tenant_id, {a.device_id for a in new_alerts if a.device_id})
    corr = await correlate_new_alerts(db, tenant_id, new_alerts, hostnames)

    # --- advance watermark ---
    wm.last_scan_at = max_observed if events else now
    wm.events_scanned = (wm.events_scanned or 0) + len(events)
    wm.alerts_created = (wm.alerts_created or 0) + len(new_alerts)
    await db.commit()

    return {
        "tenant_id": tenant_id,
        "engine": ENGINE_VERSION,
        "rules_version": rules_mod.RULES_VERSION,
        "events_scanned": len(events),
        "alerts_created": len(new_alerts),
        "rules_fired": dict(rules_fired),
        "anomaly_alerts": anomaly_fired,
        "incidents_created": corr["incidents_created"],
        "incidents_attached": corr["incidents_attached"],
        "ml_available": ml_inference.models_available(),
        "watermark": wm.last_scan_at.isoformat() if wm.last_scan_at else None,
    }
