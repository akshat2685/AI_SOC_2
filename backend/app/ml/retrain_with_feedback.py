"""Retrain SOC ML models on base data + accumulated feedback rows.

Standalone script -- run via exec, NEVER imported at boot:
    cd backend/app/ml && python3 retrain_with_feedback.py

What it does:
  1. Loads all TrainingFeedback rows (analyst-verdict / sparring / intel).
  2. Loads the base v3 dataset via threat_data.generate() (seed 42).
  3. Retrains triage / severity / IsolationForest with the SAME
     hyperparameters as train.py.
  4. REGRESSION GATE (mandatory): the new triage accuracy must be within
     2 points of the current production training_report.json accuracy, AND
     the new anomaly FPR must not increase by more than 1 point.
  5. On PASS: atomically writes the artifacts with version
     "attack-grounded-v4+feedback-N" and updates training_report.json.
  6. On FAIL: writes NOTHING and prints why. Existing artifacts are never
     deleted or modified on failure.

After a pass, bump inference.py's MODEL_VERSION to the printed version
before deploying.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(os.path.dirname(HERE))
ARTIFACTS = os.path.join(HERE, "artifacts")
sys.path.insert(0, BACKEND)  # for app.* imports (threat_data imports bare)

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix,
                             precision_recall_fscore_support)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.ml import train
from app.domain.models import TrainingFeedback
from app.ml.feedback import feedback_to_dataframe
from app.ml.threat_data import FEATURE_COLUMNS

# ---- regression gate thresholds (exact, per spec) ----
TRIAGE_ACC_TOLERANCE = 0.02   # new acc must be >= current acc - 0.02
ANOMALY_FPR_TOLERANCE = 0.01  # new FPR must be <= current FPR + 0.01


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        from app.core.config import settings
        url = getattr(settings, "DATABASE_URL", None) or getattr(
            settings, "POSTGRES_URL", None)
    except Exception as exc:  # pragma: no cover - config import failure
        raise SystemExit(f"cannot resolve DATABASE_URL: {exc}")
    if not url:
        raise SystemExit(
            "DATABASE_URL is not set and settings carry no DB URL -- aborting")
    return url


def _atomic_write(path: str, writer) -> None:
    """Write via temp file + os.replace so a crash never leaves half a file."""
    tmp = path + ".tmp"
    writer(tmp)
    os.replace(tmp, path)


def main() -> int:
    t0 = time.time()

    report_path = os.path.join(ARTIFACTS, "training_report.json")
    if not os.path.exists(report_path):
        print("GATE FAIL: no current training_report.json -- nothing to "
              "compare against. Refusing to overwrite artifacts blind.")
        return 1
    with open(report_path) as f:
        current = json.load(f)
    try:
        cur_acc = float(current["models"]["triage_clf"]["accuracy"])
        cur_fpr = float(
            current["models"]["anomaly_iforest"]["false_positive_rate_benign_holdout"])
        cur_version = current.get("model_version", "?")
    except (KeyError, TypeError, ValueError):
        print("GATE FAIL: current training_report.json is missing the "
              "metrics the gate needs. Refusing to overwrite artifacts.")
        return 1
    print(f"current production: {cur_version} "
          f"(triage acc={cur_acc:.4f}, anomaly FPR={cur_fpr:.4f})")

    # ---- 1. load feedback rows ----
    engine = create_engine(_db_url())
    with Session(engine) as s:
        fb_rows = (s.execute(
            select(TrainingFeedback).order_by(TrainingFeedback.id))
            .scalars().all())
    n_fb = len(fb_rows)
    if n_fb == 0:
        print("no feedback rows in training_feedback -- nothing to learn, "
              "artifacts untouched.")
        return 0
    fb_df = feedback_to_dataframe(fb_rows)
    src_counts = {}
    with Session(engine) as s:
        for src, cnt in s.execute(
                select(TrainingFeedback.source, func.count())
                .group_by(TrainingFeedback.source)).all():
            src_counts[src] = int(cnt)
    print(f"feedback rows: {n_fb} {src_counts}")

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
    detect_unknown = float(np.mean(iforest.predict(unknown_test) == -1))

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
    print(f"candidate: triage acc={bin_acc:.4f} (gate >= {cur_acc - TRIAGE_ACC_TOLERANCE:.4f}), "
          f"anomaly FPR={fpr_benign:.4f} (gate <= {cur_fpr + ANOMALY_FPR_TOLERANCE:.4f})")
    if failures:
        print("GATE FAIL -- writing nothing, existing artifacts untouched:")
        for f_ in failures:
            print(f"  - {f_}")
        return 1
    print("GATE PASS")

    # ---- 5. atomic artifact writes (only reachable on gate pass) ----
    os.makedirs(ARTIFACTS, exist_ok=True)
    _atomic_write(os.path.join(ARTIFACTS, "triage_clf.pkl"),
                  lambda p: joblib.dump(triage, p))
    _atomic_write(os.path.join(ARTIFACTS, "severity_clf.pkl"),
                  lambda p: joblib.dump(sev_clf, p))
    _atomic_write(os.path.join(ARTIFACTS, "anomaly_iforest.pkl"),
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
                 f"to v3 -- the live engine needs no changes."),
    }
    _atomic_write(os.path.join(ARTIFACTS, "feature_schema.json"),
                  lambda p: json.dump(schema, open(p, "w"), indent=2))

    report = {
        "model_version": new_version,
        "trained_on": (f"attack-grounded-synthetic-v3 + {n_fb} feedback rows "
                       f"(threat_data.py seed 42 + training_feedback table)"),
        "warning": "retrain on real labeled tenant data before production use",
        "n_samples": n_samples,
        "n_feedback_rows": n_fb,
        "feedback_by_source": src_counts,
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
    _atomic_write(os.path.join(ARTIFACTS, "training_report.json"),
                  lambda p: json.dump(report, open(p, "w"), indent=2))

    print("=" * 64)
    print(f"RETRAIN COMPLETE: {new_version}")
    print(f"  triage acc={bin_acc:.4f}  severity acc={sev_acc:.4f}  "
          f"anomaly detect={detect_unknown:.4f} FPR={fpr_benign:.4f}")
    print(f"  artifacts written to {ARTIFACTS} in {time.time() - t0:.1f}s")
    print("DEPLOY NOTE: bump inference.py MODEL_VERSION to "
          f"'{new_version}' before deploying.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
