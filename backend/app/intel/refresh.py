"""Daily refresh: pull feeds -> upsert into threat_intel_iocs.

One source failing never blocks the others: refresh_all() records a
per-source error and keeps going. C2 lookups served to the detection
engine go through a 10-minute in-memory cache so scans never pay a
DB round-trip per event.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import logger
from app.intel.models import ThreatIntelIoC
from app.intel.sources import (
    IntelSourceError,
    fetch_cisa_kev,
    fetch_threatfox,
    fetch_urlhaus,
)

# threat types that mark command-and-control infrastructure
C2_THREAT_TYPES = {"botnet_cc", "c2"}

C2_CACHE_TTL_S = 600

# last refresh bookkeeping (process memory; surfaced via GET /intel/status)
_LAST_REFRESH: dict[str, Optional[datetime]] = {}
_LAST_ERROR: dict[str, Optional[str]] = {}

# name -> (cached_at, set_of_values)
_C2_CACHE: dict[str, tuple[datetime, set[str]]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _source_names() -> list[str]:
    return ["cisa-kev", "threatfox", "urlhaus"]


def last_refresh_info() -> dict[str, dict[str, Optional[str]]]:
    """Per-source last refresh time / error for the status endpoint."""
    return {
        name: {
            "last_refresh_at": (
                _LAST_REFRESH[name].isoformat() if _LAST_REFRESH.get(name) else None
            ),
            "last_error": _LAST_ERROR.get(name),
        }
        for name in _source_names()
    }


async def refresh_source(db: AsyncSession, name: str) -> dict:
    """Fetch one feed and upsert its IoCs. Returns inserted/updated counts."""
    if name == "cisa-kev":
        iocs = fetch_cisa_kev()
    elif name == "threatfox":
        iocs = fetch_threatfox(auth_key=os.environ.get("THREATFOX_AUTH_KEY"))
    elif name == "urlhaus":
        iocs = fetch_urlhaus()
    else:
        raise IntelSourceError(f"unknown intel source: {name!r}")

    now = _utcnow()
    existing = (
        (await db.execute(select(ThreatIntelIoC).where(ThreatIntelIoC.source == name)))
        .scalars()
        .all()
    )
    by_key = {(r.ioc_type, r.value): r for r in existing}

    inserted = 0
    updated = 0
    deduped = 0
    new_rows: list[ThreatIntelIoC] = []
    pending_new: dict[tuple[str, str], ThreatIntelIoC] = {}
    for ioc in iocs:
        value = (ioc.get("value") or "").strip()
        if not value or len(value) > 1024:
            continue  # malformed or over column width: skip, never truncate silently
        key = (ioc["ioc_type"], value)
        new_first = ioc.get("first_seen")
        row = by_key.get(key)
        if row is None:
            pending = pending_new.get(key)
            if pending is None:
                pending_new[key] = ThreatIntelIoC(
                    source=name,
                    ioc_type=ioc["ioc_type"],
                    value=value,
                    threat_type=ioc.get("threat_type"),
                    malware_family=ioc.get("malware_family"),
                    first_seen=new_first,
                    last_seen=ioc.get("last_seen") or now,
                    raw=ioc.get("raw"),
                )
                inserted += 1
            else:
                # Same feed lists the same IoC twice (e.g. two URLs on one
                # domain): merge into the pending row, keep earliest sighting.
                if new_first and (
                    pending.first_seen is None or new_first < pending.first_seen
                ):
                    pending.first_seen = new_first
                deduped += 1
            continue
        # Re-sighting: refresh last_seen and any improved metadata.
        row.last_seen = now
        if ioc.get("threat_type"):
            row.threat_type = ioc["threat_type"]
        if ioc.get("malware_family"):
            row.malware_family = ioc["malware_family"]
        if new_first:
            # SQLite returns naive datetimes; normalize before comparing.
            existing_first = row.first_seen
            if existing_first is not None and existing_first.tzinfo is None:
                existing_first = existing_first.replace(tzinfo=timezone.utc)
            if existing_first is None or new_first < existing_first:
                row.first_seen = new_first
        if ioc.get("raw"):
            row.raw = ioc["raw"]
        updated += 1

    new_rows.extend(pending_new.values())
    if new_rows:
        db.add_all(new_rows)
    await db.commit()

    # IoC set changed -> drop the C2 cache so the engine sees fresh data.
    _C2_CACHE.clear()
    _LAST_REFRESH[name] = now
    _LAST_ERROR[name] = None
    logger.info(
        "intel_source_refreshed",
        source=name,
        inserted=inserted,
        updated=updated,
        deduped=deduped,
    )
    return {"inserted": inserted, "updated": updated, "deduped": deduped}


async def refresh_all(db: AsyncSession) -> dict:
    """Refresh every feed. A dead feed is recorded, never fatal."""
    sources: dict[str, dict] = {}
    total_inserted = 0
    total_updated = 0
    total_deduped = 0
    for name in _source_names():
        try:
            counts = await refresh_source(db, name)
            sources[name] = {"status": "ok", **counts}
            total_inserted += counts["inserted"]
            total_updated += counts["updated"]
            total_deduped += counts["deduped"]
        except IntelSourceError as exc:
            _LAST_ERROR[name] = str(exc)
            logger.error("intel_source_failed", source=name, error=str(exc))
            sources[name] = {
                "status": "error",
                "error": str(exc),
                "inserted": 0,
                "updated": 0,
                "deduped": 0,
            }
        except Exception as exc:  # never let one feed kill the loop
            _LAST_ERROR[name] = f"unexpected: {exc}"
            logger.error("intel_source_failed", source=name, exc_info=True)
            sources[name] = {
                "status": "error",
                "error": f"unexpected: {exc}",
                "inserted": 0,
                "updated": 0,
                "deduped": 0,
            }
    return {
        "sources": sources,
        "totals": {
            "inserted": total_inserted,
            "updated": total_updated,
            "deduped": total_deduped,
        },
        "refreshed_at": _utcnow().isoformat(),
    }


async def _cached_c2_set(
    db: Optional[AsyncSession], ioc_type: str
) -> set[str]:
    cache_key = f"c2_{ioc_type}s"
    cached = _C2_CACHE.get(cache_key)
    if cached and (_utcnow() - cached[0]) < timedelta(seconds=C2_CACHE_TTL_S):
        return cached[1]

    close_after = False
    if db is None:
        from app.infrastructure.database import AsyncSessionLocal

        db = AsyncSessionLocal()
        close_after = True
    try:
        rows = (
            (
                await db.execute(
                    select(ThreatIntelIoC.value).where(
                        ThreatIntelIoC.ioc_type == ioc_type,
                        (ThreatIntelIoC.threat_type.in_(C2_THREAT_TYPES))
                        | (ThreatIntelIoC.malware_family.is_not(None)),
                    )
                )
            )
            .scalars()
            .all()
        )
    finally:
        if close_after:
            await db.close()

    values = {str(v) for v in rows if v}
    _C2_CACHE[cache_key] = (_utcnow(), values)
    return values


async def get_c2_ips(db: Optional[AsyncSession] = None) -> set[str]:
    """Known C2/botnet IP addresses (10-min cache)."""
    return await _cached_c2_set(db, "ip")


async def get_c2_domains(db: Optional[AsyncSession] = None) -> set[str]:
    """Known C2/botnet domains (10-min cache)."""
    return await _cached_c2_set(db, "domain")
