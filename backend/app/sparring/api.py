"""Sparring API: run the twin, list runs, coverage across recent runs.

All findings here are SIMULATED (models.SIMULATED_MARKER). Nothing in this
router reads or writes tenant telemetry — the twin scores synthetic events
in memory. Findings never become alerts.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List

from app.api.deps import require_roles_dual
from app.api.middleware.rate_limit_middleware import limiter
from app.application.audit_logger import audit_logger
from app.core.auth import current_tenant_id, current_trace_id, current_user_id
from app.domain.models import RoleEnum
from app.infrastructure.database import get_db
from app.sparring.models import list_runs, SIMULATED_MARKER
from app.sparring.runner import get_evasion_training_rows, run_sparring
from app.sparring.simulate import TECHNIQUE_SIMULATORS

router = APIRouter()

READ_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST, RoleEnum.TENANT_VIEWER]
WRITE_ROLES = [RoleEnum.TENANT_ADMIN, RoleEnum.TENANT_ANALYST]


class SparringRunRequest(BaseModel):
    technique_ids: List[str] | None = None  # default: all 24
    include_benign: bool = True


def _finding_dict(f) -> Dict[str, Any]:
    return {
        "technique_id": f.technique_id,
        "kind": f.kind,
        "detected": f.detected,
        "detector": f.detector,
        "rule_id": f.rule_id,
        "all_rule_ids": f.all_rule_ids,
        "events_until_detection": f.events_until_detection,
        "events_total": f.events_total,
        "simulated": f.simulated,
    }


def _run_dict(run) -> Dict[str, Any]:
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_s": run.duration_s,
        "technique_count": run.technique_count,
        "detected_count": run.detected_count,
        "evasion_count": run.evasion_count,
        "benign_count": run.benign_count,
        "fp_count": run.fp_count,
        "detection_rate": run.detection_rate,
        "engine_version": run.engine_version,
        "model_version": run.model_version,
        "simulated": run.simulated,
        "findings": [_finding_dict(f) for f in run.findings],
    }


@router.post("/run")
@limiter.limit("5/minute")
async def start_sparring_run(
    request: Request,
    body: SparringRunRequest,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
) -> Dict[str, Any]:
    """Run the digital twin against the detection engine (simulated)."""
    ids = body.technique_ids or list(TECHNIQUE_SIMULATORS)
    unknown = [t for t in ids if t not in TECHNIQUE_SIMULATORS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown technique_id(s): {unknown}")
    try:
        run = run_sparring(db, technique_ids=ids, include_benign=body.include_benign)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"sparring run failed: {exc}")
    audit_logger.emit(
        action="sparring_run",
        tenant_id=current_tenant_id.get(),
        user_id=current_user_id.get(),
        trace_id=current_trace_id.get(),
        details={
            "run_id": run.id,
            "technique_count": run.technique_count,
            "detected_count": run.detected_count,
            "evasion_count": run.evasion_count,
            "fp_count": run.fp_count,
            "simulated": True,
        },
    )
    return _run_dict(run)


@router.get("/runs")
@limiter.limit("60/minute")
async def list_sparring_runs(
    request: Request,
    limit: int = 20,
    _auth=Depends(require_roles_dual(READ_ROLES)),
) -> Dict[str, Any]:
    """Recent sparring runs (in-memory; cleared on restart)."""
    runs = list_runs(limit=min(max(limit, 1), 50))
    return {
        "simulated": True,
        "marker": SIMULATED_MARKER,
        "runs": [_run_dict(r) for r in runs],
    }


@router.get("/coverage")
@limiter.limit("60/minute")
async def sparring_coverage(
    request: Request,
    _auth=Depends(require_roles_dual(READ_ROLES)),
) -> Dict[str, Any]:
    """Per-technique detection rate across recent runs + benign FP rates.

    Detection here means the engine would have raised a rule finding or an
    anomaly alert on the simulated technique — measured against synthetic
    footprints, not real attacks. Honest coverage, not a security guarantee.
    """
    runs = list_runs(limit=20)
    tech_stats: Dict[str, Dict[str, Any]] = {}
    benign_stats: Dict[str, Dict[str, int]] = {}
    for run in runs:
        for f in run.findings:
            if f.kind == "attack":
                s = tech_stats.setdefault(
                    f.technique_id,
                    {"tested": 0, "detected": 0, "rules_fired": {}},
                )
                s["tested"] += 1
                if f.detected:
                    s["detected"] += 1
                for rid in f.all_rule_ids:
                    s["rules_fired"][rid] = s["rules_fired"].get(rid, 0) + 1
            else:
                arch = f.technique_id.split("benign:", 1)[-1]
                s = benign_stats.setdefault(arch, {"tested": 0, "fps": 0, "rules_fired": {}})
                s["tested"] += 1
                if f.detected:
                    s["fps"] += 1
                    for rid in f.all_rule_ids:
                        s["rules_fired"][rid] = s["rules_fired"].get(rid, 0) + 1

    techniques = []
    for tid in sorted(tech_stats):
        s = tech_stats[tid]
        techniques.append({
            "technique_id": tid,
            "runs_tested": s["tested"],
            "detected": s["detected"],
            "detection_rate": round(s["detected"] / s["tested"], 3) if s["tested"] else None,
            # What actually caught it, across runs. A technique "detected"
            # only via first-seen-binary on a fresh virtual device is a weak
            # signal — the breakdown keeps the headline rate honest.
            "rules_fired": s["rules_fired"],
        })
    benign = []
    for arch in sorted(benign_stats):
        s = benign_stats[arch]
        benign.append({
            "archetype": arch,
            "runs_tested": s["tested"],
            "false_positives": s["fps"],
            "fp_rate": round(s["fps"] / s["tested"], 3) if s["tested"] else None,
            "rules_fired": s["rules_fired"],
        })
    return {
        "simulated": True,
        "runs_considered": len(runs),
        "techniques": techniques,
        "benign_archetypes": benign,
        "evasion_training_rows_available": len(get_evasion_training_rows()),
        "note": "Coverage measured on simulated technique footprints; not real-attack efficacy.",
    }


@router.get("/scenarios")
@limiter.limit("60/minute")
async def list_twin_scenarios(
    request: Request,
    _auth=Depends(require_roles_dual(READ_ROLES)),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    detected: bool | None = None,
) -> Dict[str, Any]:
    """Recent intel-driven twin scenarios with outcomes + evasion analysis.

    The closed loop made visible: each scenario shows where the attack
    came from (fresh intel IoC, real alert replay), whether the engine
    caught it, and — for evasions — the SOC's own analysis of what
    happened, why it evaded, and how to defend.
    """
    from sqlalchemy import desc, select

    from app.sparring.models_db import TwinScenario

    stmt = select(TwinScenario).order_by(desc(TwinScenario.created_at)).limit(min(limit, 100))
    if detected is not None:
        stmt = stmt.where(TwinScenario.detected == detected)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "simulated": True,
        "count": len(rows),
        "scenarios": [
            {
                "id": r.id,
                "source": r.source,
                "technique_id": r.technique_id,
                "tactic": r.tactic,
                "scenario": r.scenario,
                "detected": r.detected,
                "detector": r.detector,
                "rule_id": r.rule_id,
                "analysis": r.analysis,
                "training_feedback_id": r.training_feedback_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post("/intel-pass")
@limiter.limit("10/minute")
async def run_intel_pass(
    request: Request,
    _auth=Depends(require_roles_dual(WRITE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Manually trigger one intel-driven twin pass (same as the daily loop).

    Builds scenarios from the freshest intel IoCs + recent real alert
    replays, scores them against the real engine, analyzes evasions, and
    persists everything to twin_scenarios + training_feedback.
    """
    from app.sparring import defense as defense_mod
    from app.sparring import intel_driven as intel_mod
    from app.sparring.models_db import TwinScenario
    from app.sparring.runner import _evasion_row, _score_events

    ioc_scenarios = await intel_mod.build_ioc_scenarios(db)
    replay_scenarios = await intel_mod.build_replay_scenarios(db)
    scenarios = ioc_scenarios + replay_scenarios

    from app.sparring.loop import _first_tenant_id, _intel_state
    tenant_id = await _first_tenant_id(db)

    results: list[dict] = []
    training_rows: list[dict] = []
    for sc in scenarios:
        score = _score_events(sc["events"])
        analysis: dict = {}
        if not score.get("detected"):
            analysis = defense_mod.analyze_outcome(
                sc, score, await _intel_state(db, sc))
            row = _evasion_row(sc.get("technique_id") or "unknown", sc["events"])
            if row:
                training_rows.append({
                    "feature_vector": row["features"],
                    "technique_id": row["technique_id"],
                    "tactic": row["tactic"],
                    "label": "attack",
                    "severity": row["severity"],
                    "device_id": None,
                })
        rec = TwinScenario(
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
        )
        db.add(rec)
        results.append({
            "source": sc["source"],
            "technique_id": sc.get("technique_id"),
            "detected": bool(score.get("detected")),
            "rule_id": score.get("rule_id"),
            "description": sc.get("description"),
        })

    recorded = 0
    if training_rows and tenant_id is not None:
        from app.ml import feedback as feedback_mod
        res = await feedback_mod.record_sparring_rows(db, tenant_id, training_rows)
        recorded = res.get("recorded", 0)
    else:
        await db.commit()

    audit_logger.info("twin_intel_pass", extra={
        "trace_id": current_trace_id(), "user_id": current_user_id(),
        "tenant_id": current_tenant_id(),
        "scenarios": len(scenarios),
        "evasions": len(training_rows),
        "training_rows": recorded,
    })
    return {
        "simulated": True,
        "scenarios_run": len(scenarios),
        "ioc_scenarios": len(ioc_scenarios),
        "replay_scenarios": len(replay_scenarios),
        "evasions": len(training_rows),
        "training_rows_recorded": recorded,
        "results": results,
    }
