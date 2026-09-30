"""Sparring runner: twin attacks vs the REAL detection scoring path.

The scoring here is the same logic engine.scan_tenant() uses, minus the
database: rules run via rules.match_rules, the anomaly pass via
features.bucket_by_device_hour + features.build_hourly_features +
ml.predict_anomaly — the exact same pure functions, in the same order,
with the same thresholds. No twin event is ever written to the database
and no alert/incident row is ever created.

Detected = the engine would have raised something (rule finding or
anomaly alert) on the virtual device. Evasions = attack simulations the
engine missed entirely; their device-hour feature vectors are stashed as
labeled training rows (is_attack=1, technique_id, source="sparring") for
the retrain pipeline via get_evasion_training_rows().
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.detection import engine as engine_mod
from app.detection import features as features_mod
from app.detection import rules as rules_mod
from app.ml import inference as ml_inference
from app.ml.threat_data import FEATURE_COLUMNS
from app.sparring.models import (
    SparringFinding,
    SparringRun,
    get_stored_evasion_rows,
    store_evasion_rows,
    store_run,
)
from app.sparring.simulate import (
    BENIGN_ARCHETYPES,
    TECHNIQUE_SIMULATORS,
    TECHNIQUE_TACTICS,
    simulate_benign_archetype,
    simulate_technique,
)

logger = logging.getLogger(__name__)

ENGINE_VERSION = engine_mod.ENGINE_VERSION


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _score_events(events: list[dict]) -> dict:
    """Run the engine's scoring path over in-memory event dicts.

    Returns {"detected": bool, "detector": str|None, "rule_id": str|None,
    "all_rule_ids": list[str], "events_until_detection": int|None}. Mirrors
    scan_tenant's rule pass (ordered, first firing wins for the headline)
    then its anomaly pass (per device-hour). all_rule_ids records every
    rule that fired, so coverage can separate substantive detections from
    the first-seen-binary noise a fresh virtual device inevitably raises.
    """
    # --- rule pass: same call the engine makes, fresh virtual device ---
    all_rule_ids: list[str] = []
    first_hit: dict | None = None
    first_idx: int | None = None
    for i, ev in enumerate(events):
        findings = rules_mod.match_rules(ev, known_hashes=set())
        for f in findings:
            if f["rule_id"] not in all_rule_ids:
                all_rule_ids.append(f["rule_id"])
            if first_hit is None:
                first_hit, first_idx = f, i
    if first_hit is not None:
        return {
            "detected": True,
            "detector": rules_mod.RULES_VERSION,
            "rule_id": first_hit["rule_id"],
            "all_rule_ids": all_rule_ids,
            "events_until_detection": (first_idx or 0) + 1,
        }

    # --- batch rule pass: same call the engine makes (brute-force-auth) ---
    for f in rules_mod.match_batch_rules(events):
        if f["rule_id"] not in all_rule_ids:
            all_rule_ids.append(f["rule_id"])
        return {
            "detected": True,
            "detector": rules_mod.RULES_VERSION,
            "rule_id": f["rule_id"],
            "all_rule_ids": all_rule_ids,
            "events_until_detection": len(events),
        }

    # --- anomaly pass: same bucketing + features + model the engine uses ---
    if not ml_inference.models_available():
        logger.info("ml models unavailable; twin anomaly pass skipped")
        return {"detected": False, "detector": None, "rule_id": None,
                "all_rule_ids": all_rule_ids, "events_until_detection": None}
    buckets = features_mod.bucket_by_device_hour(events)
    for (device_id, hour_key), bucket in sorted(buckets.items()):
        if len(bucket) < features_mod.ANOMALY_MIN_EVENTS:
            continue
        window_start = datetime.strptime(hour_key, "%Y-%m-%dT%H").replace(
            tzinfo=timezone.utc)
        feats = features_mod.build_hourly_features(
            bucket, window_start,
            known_process_names=set(),  # fresh virtual device: nothing known
            alert_count_1h=0,
        )
        try:
            result = ml_inference.predict_anomaly(feats)
        except Exception as exc:
            logger.warning("twin anomaly inference failed: %s", exc)
            continue
        if result and result.get("is_anomaly"):
            return {
                "detected": True,
                "detector": "ml-anomaly-v1",
                "rule_id": "ml-anomaly",
                "all_rule_ids": all_rule_ids + ["ml-anomaly"],
                "events_until_detection": len(bucket),
            }
    return {"detected": False, "detector": None, "rule_id": None,
            "all_rule_ids": all_rule_ids, "events_until_detection": None}


def _evasion_row(technique_id: str, events: list[dict]) -> dict | None:
    """Build a labeled training row from an evaded attack's feature vector.

    Uses the same feature dict the engine scored and the same column order
    as the ML feature schema (via inference.build_vector), labeled
    is_attack=1 with the technique and a simulated source marker.
    """
    buckets = features_mod.bucket_by_device_hour(events)
    if not buckets:
        return None
    (device_id, hour_key), bucket = sorted(buckets.items())[0]
    window_start = datetime.strptime(hour_key, "%Y-%m-%dT%H").replace(
        tzinfo=timezone.utc)
    feats = features_mod.build_hourly_features(
        bucket, window_start, known_process_names=set(), alert_count_1h=0)
    vec = ml_inference.build_vector(feats)[0].tolist()
    return {
        "features": dict(zip(FEATURE_COLUMNS, vec)),
        "is_attack": 1,
        "tactic": TECHNIQUE_TACTICS.get(technique_id, "unknown"),
        "technique_id": technique_id,
        "severity": "HIGH",  # evasions are reviewed; severity is re-graded at train time
        "provenance": "sparring-evasion",
        "archetype": "attack",
        "source": "sparring",
        "simulated": True,
    }


def run_sparring(db=None, technique_ids: list[str] | None = None,
                 include_benign: bool = True, seed: int | None = None) -> SparringRun:
    """Run one full sparring pass.

    db: accepted for interface compatibility with future per-tenant
    calibration; currently unused — the twin scores entirely in memory
    and never reads or writes tenant data.
    technique_ids: subset of the 24 simulated techniques; default all.
    """
    ids = list(technique_ids) if technique_ids else list(TECHNIQUE_SIMULATORS)
    unknown = [t for t in ids if t not in TECHNIQUE_SIMULATORS]
    if unknown:
        raise ValueError(f"unknown technique_id(s): {unknown}")

    run = SparringRun(
        id=uuid.uuid4().hex[:12],
        started_at=_utcnow(),
        technique_count=len(ids),
        model_version=ml_inference.MODEL_VERSION,
        engine_version=ENGINE_VERSION,
    )
    evasion_rows: list[dict] = []

    for tid in ids:
        try:
            events = simulate_technique(tid, seed=seed)
        except Exception as exc:
            logger.warning("twin simulation failed for %s: %s", tid, exc)
            continue
        score = _score_events(events)
        finding = SparringFinding(
            run_id=run.id,
            technique_id=tid,
            kind="attack",
            detected=score["detected"],
            detector=score["detector"],
            rule_id=score["rule_id"],
            events_until_detection=score["events_until_detection"],
            events_total=len(events),
            all_rule_ids=score["all_rule_ids"],
        )
        if score["detected"]:
            run.detected_count += 1
        else:
            run.evasion_count += 1
            row = _evasion_row(tid, events)
            if row:
                finding.evasion_features = row
                evasion_rows.append(row)
        run.findings.append(finding)

    if include_benign:
        for arch in BENIGN_ARCHETYPES:
            try:
                events = simulate_benign_archetype(arch, seed=seed)
            except Exception as exc:
                logger.warning("twin benign sim failed for %s: %s", arch, exc)
                continue
            score = _score_events(events)
            run.benign_count += 1
            if score["detected"]:
                run.fp_count += 1
            run.findings.append(SparringFinding(
                run_id=run.id,
                technique_id=f"benign:{arch}",
                kind="benign",
                detected=score["detected"],  # a detection here IS a false positive
                detector=score["detector"],
                rule_id=score["rule_id"],
                events_until_detection=score["events_until_detection"],
                events_total=len(events),
                all_rule_ids=score["all_rule_ids"],
            ))

    run.finished_at = _utcnow()
    store_run(run)
    store_evasion_rows(evasion_rows)
    logger.info(
        "sparring run %s: %d/%d techniques detected, %d evasions, %d FPs "
        "(simulated, no real alerts)",
        run.id, run.detected_count, run.technique_count,
        run.evasion_count, run.fp_count,
    )
    return run


def get_evasion_training_rows() -> list[dict]:
    """Labeled training rows from evasions across all runs this process.

    Each row: {"features": {15 schema cols}, "is_attack": 1,
    "technique_id", "tactic", "source": "sparring", "simulated": True}.
    Feed to the retrain pipeline as additional attack-class rows (they are
    synthetic — keep the provenance label all the way through).
    """
    return get_stored_evasion_rows()
