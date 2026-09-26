"""Train SOC ML models on ATT&CK-grounded SYNTHETIC telemetry v3.

Models:
  1. triage_clf      - RandomForestClassifier predicting is_attack
                       (binary: benign vs attack).
  2. severity_clf    - RandomForestClassifier predicting severity
                       (LOW/MEDIUM/HIGH/CRITICAL, mapped from tactic).
  3. anomaly_iforest - IsolationForest trained on BENIGN-ONLY rows.
                       This is the 0-day story: it learns what "normal"
                       looks like and flags deviations it has never seen.

Everything is trained on synthetic data (see threat_data.py): 24 MITRE
ATT&CK technique footprints + 1 unknown 0-day proxy, with the benign class
spread across 5 device archetypes (windows-dev anchored on one machine's
unlabeled real telemetry, windows-office, linux-server, macos-laptop,
overnight-idle) so the models generalize to any tenant's machine, not just
one developer's box. Metrics measure how well the models separate the
CONSTRUCTED distribution -- they are NOT estimates of real-world detection
performance. Do NOT treat these models as production-ready: retrain on real
labeled tenant data before any production use.
"""

import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix,
                             precision_recall_fscore_support)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from threat_data import FEATURE_COLUMNS, generate

HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, "artifacts")

MODEL_VERSION = "attack-grounded-v3"


def build_features(df):
    """Select the 15 engineered features in the schema's EXACT column order."""
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns: {missing}")
    return df[FEATURE_COLUMNS].to_numpy(dtype=float)


def _per_class_metrics(y_true, y_pred, classes):
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=list(range(len(classes))), zero_division=0)
    return {
        c: {"precision": round(float(prec[i]), 4),
            "recall": round(float(rec[i]), 4),
            "f1": round(float(f1[i]), 4)}
        for i, c in enumerate(classes)
    }


def main():
    t0 = time.time()
    os.makedirs(ARTIFACTS, exist_ok=True)

    df = generate()  # seeded, reproducible
    n_samples = len(df)
    X = build_features(df)

    y_bin = df["is_attack"].to_numpy(dtype=int)  # 1 = attack, 0 = benign
    sev_le = LabelEncoder().fit(df["severity"])
    y_sev = sev_le.transform(df["severity"])

    idx = np.arange(n_samples)
    train_idx, test_idx = train_test_split(
        idx, test_size=0.20, random_state=42, stratify=y_bin)
    X_train, X_test = X[train_idx], X[test_idx]
    yb_train, yb_test = y_bin[train_idx], y_bin[test_idx]
    ys_train, ys_test = y_sev[train_idx], y_sev[test_idx]

    triage_classes = ["benign", "attack"]

    # ---- 1. binary triage classifier ----
    triage = RandomForestClassifier(
        n_estimators=100, max_depth=15, min_samples_leaf=5, random_state=42,
        class_weight="balanced", n_jobs=-1)
    triage.fit(X_train, yb_train)
    yb_pred = triage.predict(X_test)
    bin_acc = accuracy_score(yb_test, yb_pred)
    bin_prec, bin_rec, bin_f1, _ = precision_recall_fscore_support(
        yb_test, yb_pred, average="macro", zero_division=0)
    bin_per_class = _per_class_metrics(yb_test, yb_pred, triage_classes)
    bin_cm = confusion_matrix(yb_test, yb_pred, labels=[0, 1]).tolist()

    # ---- 2. severity classifier ----
    sev_clf = RandomForestClassifier(
        n_estimators=80, max_depth=15, min_samples_leaf=5, random_state=42,
        class_weight="balanced", n_jobs=-1)
    sev_clf.fit(X_train, ys_train)
    ys_pred = sev_clf.predict(X_test)
    sev_acc = accuracy_score(ys_test, ys_pred)
    sev_prec, sev_rec, sev_f1, _ = precision_recall_fscore_support(
        ys_test, ys_pred, average="macro", zero_division=0)
    sev_classes = list(sev_le.classes_)
    sev_per_class = _per_class_metrics(ys_test, ys_pred, sev_classes)
    sev_cm = confusion_matrix(
        ys_test, ys_pred, labels=list(range(len(sev_classes)))).tolist()

    # ---- 3. IsolationForest on BENIGN-ONLY training rows (0-day story) ----
    iforest = IsolationForest(contamination=0.05, random_state=42)
    iforest.fit(X_train[yb_train == 0])

    benign_test = X_test[yb_test == 0]
    unknown_mask = (df["technique_id"] == "unknown").to_numpy()[test_idx]
    unknown_test = X_test[unknown_mask]
    # IsolationForest: -1 = anomaly, +1 = normal
    fpr_benign = float(np.mean(iforest.predict(benign_test) == -1))
    detect_unknown = float(np.mean(iforest.predict(unknown_test) == -1))

    # ---- save artifacts (SAME filenames as v1) ----
    joblib.dump(triage, os.path.join(ARTIFACTS, "triage_clf.pkl"))
    joblib.dump(sev_clf, os.path.join(ARTIFACTS, "severity_clf.pkl"))
    joblib.dump(iforest, os.path.join(ARTIFACTS, "anomaly_iforest.pkl"))

    schema = {
        "model_version": MODEL_VERSION,
        "feature_columns": FEATURE_COLUMNS,
        "numeric_features": FEATURE_COLUMNS[:12],
        "categorical": {"src_asset_type": ["workstation", "server", "database"],
                        "one_hot_prefix": "asset_",
                        "one_hot_columns": FEATURE_COLUMNS[12:]},
        # inference.py's predict_triage indexes attack_type_classes, so the
        # binary classes live under that key for compatibility.
        "attack_type_classes": triage_classes,
        "triage_target": "is_attack (binary)",
        "severity_classes": sev_classes,
        "tactic_classes": sorted(df["tactic"].unique().tolist()),
        "technique_classes": sorted(df["technique_id"].unique().tolist()),
        "note": ("Feature order and encodings for inference. Rebuild the "
                 "feature vector in feature_columns order before calling "
                 "predict(). Trained on ATT&CK-grounded synthetic data v3: "
                 "24 technique footprints + 1 unknown proxy; benign spread "
                 "across 5 device archetypes (windows-dev, windows-office, "
                 "linux-server, macos-laptop, overnight-idle) so the model "
                 "generalizes across tenants' machines. Column order is "
                 "identical to v2 -- the live engine needs no changes."),
    }
    with open(os.path.join(ARTIFACTS, "feature_schema.json"), "w") as f:
        json.dump(schema, f, indent=2)

    report = {
        "model_version": MODEL_VERSION,
        "trained_on": "attack-grounded-synthetic-v3 (threat_data.py, seed 42)",
        "warning": "retrain on real labeled tenant data before production use",
        "n_samples": n_samples,
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "seed": 42,
        "rows_by_tactic": {k: int(v)
                           for k, v in df["tactic"].value_counts().items()},
        "rows_by_archetype": {k: int(v)
                              for k, v in df["archetype"].value_counts().items()},
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
                "trained_on": "benign-only training rows (0-day story: "
                              "learns normal, flags deviations)",
                "n_benign_train_rows": int((yb_train == 0).sum()),
                "detection_rate_unknown_holdout": round(detect_unknown, 4),
                "false_positive_rate_benign_holdout": round(fpr_benign, 4),
                "n_unknown_holdout_rows": int(len(unknown_test)),
                "n_benign_holdout_rows": int(len(benign_test)),
            },
        },
        "limitations": [
            "Training data is synthetic and ATT&CK-grounded, not real attack "
            "traffic. Metrics measure separability of the constructed "
            "distribution, NOT expected real-world detection performance.",
            "Benign class spans 5 device archetypes but is still synthetic "
            "except the windows-dev archetype (one machine's 961 UNLABELED "
            "events, assumed benign; some 'real-anchored' rows may "
            "unknowingly describe malicious activity). Real tenant machines "
            "will deviate from all 5 archetypes.",
            "25 attack classes (24 named techniques + 1 unknown proxy) cover a "
            "small subset of the full MITRE ATT&CK matrix (200+ techniques).",
            "Technique feature footprints are hand-designed approximations, "
            "not measured from real intrusions; jitter does not equal "
            "adversary variation.",
            "Retrain on real labeled tenant data before any production use.",
        ],
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(ARTIFACTS, "training_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # ---- print metrics ----
    print("=" * 64)
    print("ATT&CK-GROUNDED v3 - TRAINING REPORT (SYNTHETIC)")
    print("=" * 64)
    print(f"samples: {n_samples}  train: {len(train_idx)}  test: {len(test_idx)}")
    print()
    print("[triage_clf] is_attack RandomForest (binary)")
    print(f"  accuracy={bin_acc:.4f}  macro P={bin_prec:.4f} "
          f"R={bin_rec:.4f}  F1={bin_f1:.4f}")
    for c in triage_classes:
        m = bin_per_class[c]
        print(f"    {c:8s} P={m['precision']:.4f} R={m['recall']:.4f} "
              f"F1={m['f1']:.4f}")
    print(f"  confusion matrix {triage_classes}: {bin_cm}")
    print()
    print("[severity_clf] severity RandomForest")
    print(f"  accuracy={sev_acc:.4f}  macro P={sev_prec:.4f} "
          f"R={sev_rec:.4f}  F1={sev_f1:.4f}")
    for c in sev_classes:
        m = sev_per_class[c]
        print(f"    {c:8s} P={m['precision']:.4f} R={m['recall']:.4f} "
              f"F1={m['f1']:.4f}")
    print()
    print("[anomaly_iforest] IsolationForest (benign-only training)")
    print(f"  detection rate on unknown holdout "
          f"(n={len(unknown_test)}): {detect_unknown:.4f}")
    print(f"  false-positive rate on benign holdout "
          f"(n={len(benign_test)}): {fpr_benign:.4f}")
    print()
    print("NOTE: metrics measure separability of the constructed synthetic")
    print("distribution, not real-world performance.")
    print(f"artifacts written to {ARTIFACTS} "
          f"in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
