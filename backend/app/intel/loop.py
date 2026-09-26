"""Background intel refresh loop (lifespan-style, like the detection scan loop).

Runs inside the API process: 60s startup delay, then a full refresh every
INTEL_REFRESH_INTERVAL_S (default 24h). A failed refresh is logged and
retried on the next interval — a dead feed must never kill the API.

Wiring (done by the parent in main.py lifespan, NOT here):
    intel_task = asyncio.create_task(intel_refresh_loop())
    ...
    intel_task.cancel()
"""

from __future__ import annotations


async def intel_refresh_loop() -> None:
    """Pull every threat-intel feed once per interval, forever."""
    import asyncio as _asyncio
    import os as _os

    from app.core.logger import logger as _logger
    from app.infrastructure.database import AsyncSessionLocal as _SessionLocal
    from app.intel.refresh import refresh_all as _refresh_all

    interval = int(_os.environ.get("INTEL_REFRESH_INTERVAL_S", "86400"))
    # Let the app finish starting (and migrations run) before the first pull.
    await _asyncio.sleep(60)
    while True:
        try:
            async with _SessionLocal() as db:
                result = await _refresh_all(db)
            _logger.info(
                "intel_refresh_complete",
                inserted=result["totals"]["inserted"],
                updated=result["totals"]["updated"],
                sources={
                    name: info["status"]
                    for name, info in result["sources"].items()
                },
            )
        except Exception:
            _logger.error("intel_refresh_loop_error", exc_info=True)
        await _asyncio.sleep(interval)
