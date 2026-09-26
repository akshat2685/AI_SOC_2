"""Background sparring loop: the twin attacks with REAL threat data, daily.

Each iteration:
  1. Standard pass: 24 simulated ATT&CK techniques vs the real engine.
  2. Intel-driven pass: fresh IoCs from threat_intel_iocs + replays of
     recent real HIGH/CRITICAL alerts, each rebuilt as a twin scenario.
  3. Every scenario is scored by the real engine (_score_events).
  4. Evasions get a structured self-analysis (what happened / why it
     evaded / how to defend) via app.sparring.defense.
  5. Everything persists to twin_scenarios (survives restarts); evasion
     training rows go to training_feedback (source="sparring") so the
     next gated retrain learns them.

60s startup delay, then one full pass every SPARRING_INTERVAL_S
(default 86400 = 24h). Never raises out of the loop.
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
            await _one_pass()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sparring loop iteration failed; will retry next interval")
        await asyncio.sleep(_interval())


async def _one_pass() -> None:
    from app.infrastructure.database import AsyncSessionLocal
    from app.sparring import defense as defense_mod
    from app.sparring import intel_driven as intel_mod
    from app.sparring.models_db import TwinScenario
    from app.sparring.runner import _evasion_row, _score_events, run_sparring

    # 1. Standard simulated-technique pass (in-memory, as before).
    run = run_sparring(None)
    logger.info(
        "sparring loop: standard pass %s — %d/%d detected, %d evasions, %d FPs",
        run.id, run.detected_count, run.technique_count,
        run.evasion_count, run.fp_count,
    )

    # 2. Intel-driven pass needs the DB.
    async with AsyncSessionLocal() as db:
        ioc_scenarios = await intel_mod.build_ioc_scenarios(db)
        replay_scenarios = await intel_mod.build_replay_scenarios(db)
        scenarios = ioc_scenarios + replay_scenarios
        logger.info(
            "sparring loop: %d intel-driven scenarios (%d ioc, %d replay)",
            len(scenarios), len(ioc_scenarios), len(replay_scenarios),
        )

        # Tenant for training rows: the twin's learnings are global; they
        # are stored under the first tenant with source="sparring" so the
        # (global) retrain pipeline picks them up.
        tenant_id = await _first_tenant_id(db)

        evasion_training_rows: list[dict] = []
        for sc in scenarios:
            try:
                score = _score_events(sc["events"])
            except Exception:
                logger.exception("twin: scoring failed for scenario %s",
                                 sc.get("scenario_id"))
                continue

            analysis: dict = {}
            if not score.get("detected"):
                intel_state = await _intel_state(db, sc)
                analysis = defense_mod.analyze_outcome(sc, score, intel_state)
                row = _evasion_row(sc.get("technique_id") or "unknown",
                                   sc["events"])
                if row:
                    evasion_training_rows.append({
                        "feature_vector": row["features"],
                        "technique_id": row["technique_id"],
                        "tactic": row["tactic"],
                        "label": "attack",
                        "severity": row["severity"],
                        "device_id": None,
                    })

            db.add(TwinScenario(
                source=sc["source"],
                technique_id=sc.get("technique_id"),
                tactic=sc.get("tactic"),
                scenario={
                    "scenario_id": sc.get("scenario_id"),
                    "description": sc.get("description"),
                    "ioc": sc.get("ioc"),
                    "replay_of_alert_id": sc.get("replay_of_alert_id"),
                    "rule_id": sc.get("rule_id"),
                    "event_count": len(sc["events"]),
                    "simulated": True,
                },
                detected=bool(score.get("detected")),
                detector=score.get("detector"),
                rule_id=score.get("rule_id"),
                analysis=analysis,
            ))

        if evasion_training_rows and tenant_id is not None:
            from app.ml import feedback as feedback_mod
            try:
                res = await feedback_mod.record_sparring_rows(
                    db, tenant_id, evasion_training_rows)
                logger.info("sparring loop: recorded %d evasion training rows",
                            res.get("recorded"))
            except Exception:
                logger.exception("sparring loop: failed to record training rows")

        await db.commit()
        logger.info("sparring loop: intel pass persisted %d scenarios",
                    len(scenarios))


async def _first_tenant_id(db) -> int | None:
    from sqlalchemy import select

    from app.domain.models import Tenant
    try:
        row = (await db.execute(
            select(Tenant.id).order_by(Tenant.id).limit(1))).scalar_one_or_none()
        return row
    except Exception:
        return None


async def _intel_state(db, scenario: dict) -> dict:
    """Is the scenario's IoC still in the feed? (for evasion analysis)"""
    if scenario.get("source") != "intel-ioc":
        return {}
    from sqlalchemy import select

    from app.domain.models import ThreatIntelIoC
    ioc = scenario.get("ioc") or {}
    try:
        exists = (await db.execute(
            select(ThreatIntelIoC.id)
            .where(ThreatIntelIoC.ioc_type == ioc.get("type"),
                   ThreatIntelIoC.value == ioc.get("value"))
            .limit(1))).scalar_one_or_none()
        return {"ioc_in_feed": exists is not None}
    except Exception:
        return {}
