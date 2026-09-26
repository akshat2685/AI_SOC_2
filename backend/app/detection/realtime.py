"""Ingest-time realtime scoring: the fast path of the autonomous defense loop.

The 5-minute scan loop (engine.scan_tenant) is the thorough backstop. This
module is the real-time path: it runs the cheap rules over the batch that
was JUST ingested — before the HTTP response returns — so a HIGH/CRITICAL
finding becomes an alert, a response-policy decision, and an incident
within seconds instead of minutes.

Pipeline per call:
  1. rules-v1 over the batch (no ML — keeps p99 < 100ms for 50 events),
  2. HIGH/CRITICAL findings -> Alert rows via engine.build_rule_alert
     (same fingerprint space as the scan loop, so the scan never
     double-alerts what realtime already caught),
  3. db.flush() so alert ids exist,
  4. response policy per alert (auto command or approval request),
  5. correlate into incidents (same function the scan uses).

The caller's commit persists everything atomically; this function only
flushes. It NEVER raises — any failure logs and returns what it managed.

Wiring (parent): call score_ingested_batch() in the ingest route after
db.flush() of the accepted events, before the route's commit.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.detection import engine as engine_mod
from app.detection import rules as rules_mod
from app.detection.correlate import correlate_new_alerts
from app.domain.models import Alert, SecurityEvent
from app.response.policy import evaluate_response_policy

logger = logging.getLogger(__name__)

REALTIME_SEVERITIES = ("HIGH", "CRITICAL")
MAX_BATCH_EVENTS = 200  # safety cap; the ingest route caps batches lower


async def score_ingested_batch(
    db: AsyncSession,
    tenant_id: int,
    device_id: str,
    events: list[SecurityEvent],
) -> list[Alert]:
    """Score a just-ingested batch with rules-v1. Returns the alerts created."""
    started = time.monotonic()
    try:
        return await _score(db, tenant_id, device_id, events)
    except Exception as exc:  # never break ingest
        logger.exception("realtime_scoring_failed", tenant_id=tenant_id,
                         device_id=device_id, error=str(exc))
        return []
    finally:
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms > 100:
            logger.warning("realtime_scoring_slow", tenant_id=tenant_id,
                           device_id=device_id, elapsed_ms=round(elapsed_ms, 1))


async def _score(
    db: AsyncSession,
    tenant_id: int,
    device_id: str,
    events: list[SecurityEvent],
) -> list[Alert]:
    events = events[:MAX_BATCH_EVENTS]
    if not events:
        return []

    now = datetime.now(timezone.utc)
    # Same dedup window as the scan loop: realtime alerts land in the same
    # fingerprint space, so the 5-minute scan skips them (no double alerts).
    seen_fps = await engine_mod._recent_fingerprints(
        db, tenant_id, now - engine_mod.DEDUP_WINDOW
    )

    new_alerts: list[Alert] = []
    event_dicts: list[dict] = []
    try:
        from app.intel.refresh import get_c2_domains as _rt_c2_domains
        from app.intel.refresh import get_c2_ips as _rt_c2_ips

        c2_ips = await _rt_c2_ips(db)
        c2_domains = await _rt_c2_domains(db)
    except Exception:
        logger.warning("realtime_intel_c2_lookup_failed", exc_info=True)
        c2_ips, c2_domains = set(), set()
    for e in events:
        ev = engine_mod._event_to_dict(e)
        event_dicts.append(ev)
        for finding in rules_mod.match_rules(ev):  # no known_hashes: core 3 rules only
            if finding["severity"] not in REALTIME_SEVERITIES:
                continue
            fp = finding["fingerprint"]
            if fp in seen_fps:
                continue
            seen_fps.add(fp)
            alert = engine_mod.build_rule_alert(tenant_id, ev, finding)
            db.add(alert)
            new_alerts.append(alert)
        for finding in rules_mod.match_ioc_rules(ev, c2_ips, c2_domains):
            if finding["severity"] not in REALTIME_SEVERITIES:
                continue
            fp = finding["fingerprint"]
            if fp in seen_fps:
                continue
            seen_fps.add(fp)
            alert = engine_mod.build_rule_alert(tenant_id, ev, finding)
            db.add(alert)
            new_alerts.append(alert)

    # Batch rules (brute-force-auth) over the ingested set.
    for finding in rules_mod.match_batch_rules(event_dicts):
        if finding["severity"] not in REALTIME_SEVERITIES:
            continue
        fp = finding["fingerprint"]
        if fp in seen_fps:
            continue
        seen_fps.add(fp)
        alert = engine_mod.build_rule_alert(
            tenant_id, {"id": None, "device_id": finding["device_id"]}, finding
        )
        db.add(alert)
        new_alerts.append(alert)

    if not new_alerts:
        return []

    await db.flush()  # assign alert ids before policy + correlation

    for alert in new_alerts:
        await evaluate_response_policy(db, alert)

    hostnames = await engine_mod._hostnames(db, tenant_id, {device_id})
    await correlate_new_alerts(db, tenant_id, new_alerts, hostnames)

    logger.info(
        "realtime_scored",
        tenant_id=tenant_id,
        device_id=device_id,
        events=len(events),
        alerts=len(new_alerts),
    )
    return new_alerts
