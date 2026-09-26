"""Feature building for the Phase 2 anomaly signal.

Pure functions over plain event dicts. The feature names match
backend/app/ml/artifacts/feature_schema.json exactly; anything the sensor
cannot observe (bytes, DNS) is honestly 0, never invented.

The anomaly model (IsolationForest, synthetic-v1) was fit on benign-only
traffic. Findings from it are labeled detector="ml-anomaly-v1" with the
model version attached, so nobody mistakes them for signature detections.
"""

from __future__ import annotations

from datetime import datetime, timezone

ANOMALY_MIN_EVENTS = 5  # don't score near-empty windows: noise, not signal


def _hour_key(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")


def bucket_by_device_hour(events: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Group events by (device_id, UTC hour)."""
    buckets: dict[tuple[str, str], list[dict]] = {}
    for e in events:
        ts = e.get("observed_at")
        if not isinstance(ts, datetime):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        key = (str(e.get("device_id") or "unknown"), _hour_key(ts))
        buckets.setdefault(key, []).append(e)
    return buckets


def _section(event: dict) -> dict:
    """Typed section of an event; stored payloads are unwrapped, raw sensor
    records nest the section under its type key. Handle both."""
    payload = event.get("payload") or {}
    key = {
        "process": "process", "network": "network", "file": "file",
        "auth": "auth", "dns": "dns",
    }.get(str(event.get("event_type") or ""))
    if key and isinstance(payload.get(key), dict):
        return payload[key]
    return payload if isinstance(payload, dict) else {}


def build_hourly_features(
    window_events: list[dict],
    window_start: datetime,
    known_process_names: set[str],
    alert_count_1h: int = 0,
) -> dict:
    """Aggregate one device-hour of events into the model's feature vector.

    known_process_names: process names seen for this device in the trailing
    30 days (for new_process_rarity). alert_count_1h: alerts already raised
    for this device in the same hour.
    """
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    hour = window_start.hour
    weekday = window_start.weekday()

    failed_logins = 0
    dst_ips: set[str] = set()
    proc_names: list[str] = []
    new_proc = 0

    for e in window_events:
        et = e.get("event_type")
        if et == "auth":
            a = _section(e)
            if a.get("result") in ("failed", "failure", "denied"):
                failed_logins += 1
        elif et == "network":
            n = _section(e)
            if n.get("dst_ip"):
                dst_ips.add(str(n["dst_ip"]))
        elif et == "process":
            p = _section(e)
            name = str(p.get("name") or "").lower()
            if name:
                proc_names.append(name)
                if name not in known_process_names:
                    new_proc += 1

    new_process_rarity = (new_proc / len(proc_names)) if proc_names else 0.0

    return {
        "hour_of_day": float(hour),
        "day_of_week": float(weekday),
        "off_hours": 1.0 if (hour < 7 or hour >= 19) else 0.0,
        "failed_logins_1h": float(failed_logins),
        "unique_dst_ips_1h": float(len(dst_ips)),
        "bytes_out_mb_1h": 0.0,  # sensor reports honest nulls; never invented
        "new_process_rarity": round(new_process_rarity, 3),
        "dns_query_entropy": 0.0,  # no DNS capture yet; never invented
        "alert_count_1h": float(alert_count_1h),
        "src_asset_type": "workstation",
    }
