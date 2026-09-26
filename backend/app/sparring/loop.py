"""Background sparring loop: the twin attacks the digital twin daily.

Lifespan-style coroutine — the parent wires it into app lifespan (the same
pattern as the detection scan loop in main.py). 60s startup delay, then one
full sparring pass every SPARRING_INTERVAL_S (default 86400 = 24h).

Never raises out of the loop: per-technique failures are already contained
in run_sparring, and the whole iteration is wrapped defensively so one bad
pass can never kill the scheduler.
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

STARTUP_DELAY_S = 60
DEFAULT_INTERVAL_S = 86400  # 24h


def _interval() -> int:
    try:
        return max(3600, int(os.environ.get("SPARRING_INTERVAL_S", str(DEFAULT_INTERVAL_S))))
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL_S


async def sparring_loop() -> None:
    """Run the twin on a schedule, forever. Wire into app lifespan."""
    await asyncio.sleep(STARTUP_DELAY_S)
    while True:
        try:
            from app.sparring.runner import run_sparring

            run = run_sparring(None)  # db unused; twin is in-memory only
            logger.info(
                "sparring loop: run %s finished — %d/%d techniques detected, "
                "%d evasions, %d FPs (simulated)",
                run.id, run.detected_count, run.technique_count,
                run.evasion_count, run.fp_count,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sparring loop iteration failed; will retry next interval")
        await asyncio.sleep(_interval())
