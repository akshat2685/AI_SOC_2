"""Callable gated retrain: base data + accumulated feedback -> artifacts.

This is the engine behind both the standalone CLI
(retrain_with_feedback.py) and the automatic trigger
(app/ml/auto_retrain.py). One implementation, two callers.

Contract:
  - Reads the CURRENT artifacts' training_report.json as the gate
    baseline. Missing/unreadable baseline -> status "no_baseline",
    nothing written (refusing to overwrite blind).
  - Zero feedback rows -> status "no_feedback", nothing written.
  - REGRESSION GATE (mandatory, unchanged from the original script):
    new triage accuracy must be >= current - 0.02 AND new anomaly FPR
    must be <= current + 0.01. On failure -> status "gate_failed",
    NOTHING is written; existing artifacts are never touched.
  - On pass -> artifacts are written atomically (temp file + replace)
    with version "attack-grounded-v4+feedback-N" and
    training_report.json is updated. Returns status "passed".

The caller owns persistence of the outcome (ml_retrain_runs) and the
inference cache reload (app.ml.inference.reload_models).
"""

from __future__ import annotations

import json
import logging
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix,
                             precision_recall_fscore_support)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from app.ml import train
from app.ml.feedback import feedback_to_dataframe
from app.ml.threat_data import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, "artifacts")

# ---- regression gate thresholds (exact, per spec — do not loosen) ----
TRIAGE_ACC_TOLERANCE = 0.02   # new acc must be >= current acc - 0.02
ANOMALY_FPR_TOLERANCE = 0.01  # new FPR must be <= current FPR + 0.01


def _atomic_write(path: str, writer) -> None:
    """Write via temp file + os.replace so a crash never leaves half a file."""
    tmp = path + ".tmp"
    writer(tmp)
    os.replace(tmp, path)


def run_retrain(feedback_rows, feedback_by_source: dict | None = None,
                artifacts_dir: str = ARTIFACTS) -> dict:
    """Run the gated retrain over the given TrainingFeedback rows.

    Returns an outcome dict; never raises for gate/baseline/no-data
    outcomes (those are statuses). Unexpected exceptions propagate so
    the caller can record them as errors.
    """
    t0 = time.time()
    outcome: dict = {
        "status": "error",
        "rows_used": 0,
        "feedback_by_source": dict(feedback_by_source or {}),
        "model_version_before": None,
        "model_version_after": None,
        "triage_accuracy": None,
        "anomaly_fpr": None,
        "gate_failures": [],
        "elapsed_seconds": None,
    }

    report_path = os.path.join(artifacts_dir, "training_report.json")
    if not os.path.exists(report_path):
        outcome["status"] = "no_baseline"
        outcome["gate_failures"] = [
            "no current training_report.json — nothing to compare "
            "against; refusing to overwrite artifacts blind"]
        outcome["elapsed_seconds"] = round(time.time() - t0, 1)
        return outcome
    with open(report_path) as f:
        current = json.load(f)
    try:
        cur_acc = float(current["models"]["triage_clf"]["accuracy"])
        cur_fpr = float(
            current["models"]["anomaly_iforest"]["false_positive_rate_benign_holdout"])
        cur_version = current.get("model_version", "?")
    except (KeyError, TypeError, ValueError):
        outcome["status"] = "no_baseline"
        outcome["gate_failures"] = [
            "current training_report.json is missing the metrics the "
            "gate needs; refusing to overwrite artifacts"]
        outcome["elapsed_seconds"] = round(time.time() - t0, 1)
        return outcome
    outcome["model_version_before"] = cur_version
    logger.info("retrain: current production %s (triage acc=%.4f, anomaly FPR=%.4f)",
                cur_version, cur_acc, cur_fpr)

    # ---- 1. feedback rows ----
    fb_rows = list(feedback_rows)
    n_fb = len(fb_rows)
    outcome["rows_used"] = n_fb
    if n_fb == 0:
        outcome["status"] = "no_feedback"
        outcome["elapsed_seconds"] = round(time.time() - t0, 1)
        return outcome
    fb_df = feedback_to_dataframe(fb_rows)
    if not outcome["feedback_by_source"]:
        outcome["feedback_by_source"] = {"all": n_fb}
    logger.info("retrain: feedback rows: %d %s", n_fb, outcome["feedback_by_source"])

    new_version = f"attack-grounded-v4+feedback-{n_fb}"

    # ---- 2. base data + feedback ----
    df = pd.concat([train.generate(), fb_df], ignore_index=True)
    n_samples = len(df)
    X = train.build_features(df)
    y_bin = df["is_attack"].to_numpy(dtype=int)
    sev_le = LabelEncoder().fit(df["severity"])
    y_sev = sev_le.transform(df["severity"])

    idx = np.arange(n_samples)
    train_idx, test_idx = train_test_split(
        idx, test_size=0.20, random_state=42, stratify=y_bin)
    X_train, X_test = X[train_idx], X[test_idx]
    yb_train, yb_test = y_bin[train_idx], y_bin[test_idx]
    ys_train, ys_test = y_sev[train_idx], y_sev[test_idx]

    triage_classes = ["benign", "attack"]

    # ---- 3. retrain (hyperparams identical to train.py) ----
    triage = RandomForestClassifier(
        n_estimators=100, max_depth=15, min_samples_leaf=5, random_state=42,
        class_weight="balanced", n_jobs=-1)
    triage.fit(X_train, yb_train)
    yb_pred = triage.predict(X_test)
    bin_acc = accuracy_score(yb_test, yb_pred)
    bin_prec, bin_rec, bin_f1, _ = precision_recall_fscore_support(
        yb_test, yb_pred, average="macro", zero_division=0)
    bin_per_class = train._per_class_metrics(yb_test, yb_pred, triage_classes)
    bin_cm = confusion_matrix(yb_test, yb_pred, labels=[0, 1]).tolist()

    sev_clf = RandomForestClassifier(
        n_estimators=80, max_depth=15, min_samples_leaf=5, random_state=42,
        class_weight="balanced", n_jobs=-1)
    sev_clf.fit(X_train, ys_train)
    ys_pred = sev_clf.predict(X_test)
    sev_acc = accuracy_score(ys_test, ys_pred)
    sev_prec, sev_rec, sev_f1, _ = precision_recall_fscore_support(
        ys_test, ys_pred, average="macro", zero_division=0)
    sev_classes = list(sev_le.classes_)
    sev_per_class = train._per_class_metrics(ys_test, ys_pred, sev_classes)
    sev_cm = confusion_matrix(
        ys_test, ys_pred, labels=list(range(len(sev_classes)))).tolist()

    iforest = IsolationForest(contamination=0.05, random_state=42)
    iforest.fit(X_train[yb_train == 0])
    benign_test = X_test[yb_test == 0]
    unknown_mask = (df["technique_id"] == "unknown").to_numpy()[test_idx]
    unknown_test = X_test[unknown_mask]
    fpr_benign = float(np.mean(iforest.predict(benign_test) == -1))
    detect_unknown = (float(np.mean(iforest.predict(unknown_test) == -1))
                      if len(unknown_test) else 0.0)

    outcome["triage_accuracy"] = round(float(bin_acc), 4)
    outcome["anomaly_fpr"] = round(fpr_benign, 4)

    # ---- 4. REGRESSION GATE (mandatory) ----
    failures = []
    if bin_acc < cur_acc - TRIAGE_ACC_TOLERANCE:
        failures.append(
            f"triage accuracy {bin_acc:.4f} < {cur_acc:.4f} - "
            f"{TRIAGE_ACC_TOLERANCE:.2f} (regressed)")
    if fpr_benign > cur_fpr + ANOMALY_FPR_TOLERANCE:
        failures.append(
            f"anomaly FPR {fpr_benign:.4f} > {cur_fpr:.4f} + "
            f"{ANOMALY_FPR_TOLERANCE:.2f} (regressed)")
    logger.info(
        "retrain: candidate triage acc=%.4f (gate >= %.4f), anomaly FPR=%.4f (gate <= %.4f)",
        bin_acc, cur_acc - TRIAGE_ACC_TOLERANCE, fpr_benign,
        cur_fpr + ANOMALY_FPR_TOLERANCE)
    if failures:
        outcome["status"] = "gate_failed"
        outcome["gate_failures"] = failures
        outcome["elapsed_seconds"] = round(time.time() - t0, 1)
        logger.warning("retrain: GATE FAIL — writing nothing: %s", failures)
        return outcome
    logger.info("retrain: GATE PASS")

    # ---- 5. atomic artifact writes (only reachable on gate pass) ----
    os.makedirs(artifacts_dir, exist_ok=True)
    _atomic_write(os.path.join(artifacts_dir, "triage_clf.pkl"),
                  lambda p: joblib.dump(triage, p))
    _atomic_write(os.path.join(artifacts_dir, "severity_clf.pkl"),
                  lambda p: joblib.dump(sev_clf, p))
    _atomic_write(os.path.join(artifacts_dir, "anomaly_iforest.pkl"),
                  lambda p: joblib.dump(iforest, p))

    schema = {
        "model_version": new_version,
        "feature_columns": FEATURE_COLUMNS,
        "numeric_features": FEATURE_COLUMNS[:12],
        "categorical": {"src_asset_type": ["workstation", "server", "database"],
                        "one_hot_prefix": "asset_",
                        "one_hot_columns": FEATURE_COLUMNS[12:]},
        "attack_type_classes": triage_classes,
        "triage_target": "is_attack (binary)",
        "severity_classes": sev_classes,
        "tactic_classes": sorted(df["tactic"].unique().tolist()),
        "technique_classes": sorted(df["technique_id"].unique().tolist()),
        "note": (f"Retrained on base synthetic v3 + {n_fb} feedback rows "
                 f"(analyst-verdict/sparring/intel). Column order identical "
                 f"to v3 — the live engine needs no changes."),
    }
    _atomic_write(os.path.join(artifacts_dir, "feature_schema.json"),
                  lambda p: json.dump(schema, open(p, "w"), indent=2))

    report = {
        "model_version": new_version,
        "trained_on": (f"attack-grounded-synthetic-v3 + {n_fb} feedback rows "
                       f"(threat_data.py seed 42 + training_feedback table)"),
        "warning": "retrain on real labeled tenant data before production use",
        "n_samples": n_samples,
        "n_feedback_rows": n_fb,
        "feedback_by_source": outcome["feedback_by_source"],
        "base_version": cur_version,
        "gate": {
            "triage_acc_tolerance": TRIAGE_ACC_TOLERANCE,
            "anomaly_fpr_tolerance": ANOMALY_FPR_TOLERANCE,
            "baseline_triage_acc": round(cur_acc, 4),
            "baseline_anomaly_fpr": round(cur_fpr, 4),
            "result": "PASS",
        },
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "seed": 42,
        "rows_by_tactic": {k: int(v)
                           for k, v in df["tactic"].value_counts().items()},
        "rows_by_provenance": {k: int(v)
                               for k, v in df["provenance"].value_counts().items()},
        "rows_by_severity": {k: int(v)
                             for k, v in df["severity"].value_counts().items()},
        "models": {
            "triage_clf": {
                "type": "RandomForestClassifier",
                "params": {"n_estimators": 100, "max_depth": 15, "min_samples_leaf": 5, "random_state": 42,
                           "class_weight": "balanced", "n_jobs": -1},
                "target": "is_attack (binary)",
                "classes": triage_classes,
                "accuracy": round(float(bin_acc), 4),
                "macro_precision": round(float(bin_prec), 4),
                "macro_recall": round(float(bin_rec), 4),
                "macro_f1": round(float(bin_f1), 4),
                "per_class": bin_per_class,
                "confusion_matrix": bin_cm,
                "confusion_matrix_labels": triage_classes,
            },
            "severity_clf": {
                "type": "RandomForestClassifier",
                "params": {"n_estimators": 80, "max_depth": 15, "min_samples_leaf": 5, "random_state": 42,
                           "class_weight": "balanced", "n_jobs": -1},
                "target": "severity",
                "classes": sev_classes,
                "accuracy": round(float(sev_acc), 4),
                "macro_precision": round(float(sev_prec), 4),
                "macro_recall": round(float(sev_rec), 4),
                "macro_f1": round(float(sev_f1), 4),
                "per_class": sev_per_class,
                "confusion_matrix": sev_cm,
                "confusion_matrix_labels": sev_classes,
            },
            "anomaly_iforest": {
                "type": "IsolationForest",
                "params": {"contamination": 0.05, "random_state": 42},
                "trained_on": "benign-only training rows (base + feedback)",
                "n_benign_train_rows": int((yb_train == 0).sum()),
                "detection_rate_unknown_holdout": round(detect_unknown, 4),
                "false_positive_rate_benign_holdout": round(fpr_benign, 4),
                "n_unknown_holdout_rows": int(len(unknown_test)),
                "n_benign_holdout_rows": int(len(benign_test)),
            },
        },
        "limitations": [
            "Feedback rows are analyst judgments / simulator outputs, not "
            "ground truth: a mislabeled verdict teaches the model the wrong "
            "lesson. The regression gate bounds the damage but cannot detect "
            "a confident wrong label.",
            "Small feedback counts are drowned out by the 40k-row synthetic "
            "base; a genuinely new attack pattern needs dozens of rows "
            "before the model shifts.",
            "Training data remains synthetic + ATT&CK-grounded. Metrics "
            "measure separability of the constructed distribution, NOT "
            "expected real-world detection performance.",
        ],
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    _atomic_write(os.path.join(artifacts_dir, "training_report.json"),
                  lambda p: json.dump(report, open(p, "w"), indent=2))

    outcome["status"] = "passed"
    outcome["model_version_after"] = new_version
    outcome["elapsed_seconds"] = round(time.time() - t0, 1)
    logger.info("retrain: COMPLETE %s (triage acc=%.4f, severity acc=%.4f, "
                "anomaly detect=%.4f FPR=%.4f) in %.1fs",
                new_version, bin_acc, sev_acc, detect_unknown, fpr_benign,
                time.time() - t0)
    return outcome
