"""Train SOC ML models on SYNTHETIC telemetry.

Models:
  1. triage_clf      - RandomForestClassifier predicting attack_type
                       (8 classes incl. unknown_anomaly).
  2. severity_clf    - RandomForestClassifier predicting severity
                       (low/medium/high/critical).
  3. anomaly_iforest - IsolationForest trained on BENIGN-ONLY rows.
                       This is the 0-day story: it learns what "normal"
                       looks like and flags deviations it has never seen.

Everything is trained on synthetic data (see synth_data.py). Metrics are
printed to stdout and written to artifacts/training_report.json. Do NOT
treat these models as production-ready: retrain on real labeled tenant
data before any production use.
"""

import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (accuracy_score, classification_report,
                             precision_recall_fscore_support)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from synth_data import generate

HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS = os.path.join(HERE, "artifacts")

NUMERIC_FEATURES = [
    "hour_of_day",
    "day_of_week",
    "off_hours",
    "failed_logins_1h",
    "unique_dst_ips_1h",
    "bytes_out_mb_1h",
    "new_process_rarity",
    "dns_query_entropy",
    "alert_count_1h",
]
ASSET_ONEHOT = ["asset_workstation", "asset_server", "asset_database"]
FEATURE_COLUMNS = NUMERIC_FEATURES + ASSET_ONEHOT


def build_features(df):
    """One-hot encode src_asset_type with a FIXED column order."""
    dummies = pd.get_dummies(df["src_asset_type"], prefix="asset").astype(int)
    for col in ASSET_ONEHOT:  # ensure all columns exist even if a class is absent
        if col not in dummies:
            dummies[col] = 0
    X = pd.concat([df[NUMERIC_FEATURES].reset_index(drop=True),
                   dummies[ASSET_ONEHOT].reset_index(drop=True)], axis=1)
    return X[FEATURE_COLUMNS].to_numpy(dtype=float)


def main():
    t0 = time.time()
    os.makedirs(ARTIFACTS, exist_ok=True)

    df = generate()  # seeded, reproducible
    n_samples = len(df)
    X = build_features(df)

    atk_le = LabelEncoder().fit(df["attack_type"])
    sev_le = LabelEncoder().fit(df["severity"])
    y_atk = atk_le.transform(df["attack_type"])
    y_sev = sev_le.transform(df["severity"])

    idx = np.arange(n_samples)
    train_idx, test_idx = train_test_split(
        idx, test_size=0.20, random_state=42, stratify=y_atk)
    X_train, X_test = X[train_idx], X[test_idx]
    ya_train, ya_test = y_atk[train_idx], y_atk[test_idx]
    ys_train, ys_test = y_sev[train_idx], y_sev[test_idx]

    # ---- 1. attack-type triage classifier ----
    triage = RandomForestClassifier(
        n_estimators=150, random_state=42, class_weight="balanced", n_jobs=-1)
    triage.fit(X_train, ya_train)
    ya_pred = triage.predict(X_test)
    atk_acc = accuracy_score(ya_test, ya_pred)
    atk_prec, atk_rec, atk_f1, _ = precision_recall_fscore_support(
        ya_test, ya_pred, average="macro", zero_division=0)
    rep = classification_report(
        ya_test, ya_pred, target_names=atk_le.classes_, zero_division=0,
        output_dict=True)
    per_class_recall = {c: round(rep[c]["recall"], 4) for c in atk_le.classes_}

    # ---- 2. severity classifier ----
    sev_clf = RandomForestClassifier(
        n_estimators=150, random_state=42, class_weight="balanced", n_jobs=-1)
    sev_clf.fit(X_train, ys_train)
    ys_pred = sev_clf.predict(X_test)
    sev_acc = accuracy_score(ys_test, ys_pred)
    sev_prec, sev_rec, sev_f1, _ = precision_recall_fscore_support(
        ys_test, ys_pred, average="macro", zero_division=0)

    # ---- 3. IsolationForest on BENIGN-ONLY training rows (0-day story) ----
    benign_idx = list(atk_le.classes_).index("benign")
    unknown_idx = list(atk_le.classes_).index("unknown_anomaly")
    iforest = IsolationForest(contamination=0.05, random_state=42)
    iforest.fit(X_train[ya_train == benign_idx])

    benign_test = X_test[ya_test == benign_idx]
    unknown_test = X_test[ya_test == unknown_idx]
    # IsolationForest: -1 = anomaly, +1 = normal
    fpr_benign = float(np.mean(iforest.predict(benign_test) == -1))
    detect_unknown = float(np.mean(iforest.predict(unknown_test) == -1))

    # ---- save artifacts ----
    joblib.dump(triage, os.path.join(ARTIFACTS, "triage_clf.pkl"))
    joblib.dump(sev_clf, os.path.join(ARTIFACTS, "severity_clf.pkl"))
    joblib.dump(iforest, os.path.join(ARTIFACTS, "anomaly_iforest.pkl"))

    schema = {
        "feature_columns": FEATURE_COLUMNS,
        "numeric_features": NUMERIC_FEATURES,
        "categorical": {"src_asset_type": ["workstation", "server", "database"],
                        "one_hot_prefix": "asset_"},
        "attack_type_classes": list(atk_le.classes_),
        "severity_classes": list(sev_le.classes_),
        "note": ("Feature order and encodings for inference. Rebuild the "
                 "feature vector in feature_columns order before calling "
                 "predict(). Trained on synthetic data only."),
    }
    with open(os.path.join(ARTIFACTS, "feature_schema.json"), "w") as f:
        json.dump(schema, f, indent=2)

    report = {
        "trained_on": "synthetic-soc-telemetry-v1",
        "warning": "retrain on real tenant data before production use",
        "n_samples": n_samples,
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "seed": 42,
        "models": {
            "triage_clf": {
                "type": "RandomForestClassifier",
                "params": {"n_estimators": 150, "random_state": 42,
                           "class_weight": "balanced"},
                "target": "attack_type",
                "accuracy": round(float(atk_acc), 4),
                "macro_precision": round(float(atk_prec), 4),
                "macro_recall": round(float(atk_rec), 4),
                "macro_f1": round(float(atk_f1), 4),
                "per_class_recall": per_class_recall,
            },
            "severity_clf": {
                "type": "RandomForestClassifier",
                "params": {"n_estimators": 150, "random_state": 42,
                           "class_weight": "balanced"},
                "target": "severity",
                "accuracy": round(float(sev_acc), 4),
                "macro_precision": round(float(sev_prec), 4),
                "macro_recall": round(float(sev_rec), 4),
                "macro_f1": round(float(sev_f1), 4),
            },
            "anomaly_iforest": {
                "type": "IsolationForest",
                "params": {"contamination": 0.05, "random_state": 42},
                "trained_on": "benign-only training rows (0-day story: "
                              "learns normal, flags deviations)",
                "n_benign_train_rows": int((ya_train == benign_idx).sum()),
                "detection_rate_unknown_anomaly_holdout": round(detect_unknown, 4),
                "false_positive_rate_benign_holdout": round(fpr_benign, 4),
                "n_unknown_holdout_rows": int(len(unknown_test)),
                "n_benign_holdout_rows": int(len(benign_test)),
            },
        },
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(ARTIFACTS, "training_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # ---- print metrics ----
    print("=" * 64)
    print("SYNTHETIC SOC TELEMETRY - TRAINING REPORT")
    print("=" * 64)
    print(f"samples: {n_samples}  train: {len(train_idx)}  test: {len(test_idx)}")
    print()
    print("[triage_clf] attack_type RandomForest")
    print(f"  accuracy={atk_acc:.4f}  macro P={atk_prec:.4f} "
          f"R={atk_rec:.4f}  F1={atk_f1:.4f}")
    print("  per-class recall:")
    for c in atk_le.classes_:
        print(f"    {c:16s} {per_class_recall[c]:.4f}")
    print()
    print("[severity_clf] severity RandomForest")
    print(f"  accuracy={sev_acc:.4f}  macro P={sev_prec:.4f} "
          f"R={sev_rec:.4f}  F1={sev_f1:.4f}")
    print()
    print("[anomaly_iforest] IsolationForest (benign-only training)")
    print(f"  detection rate on unknown_anomaly holdout "
          f"(n={len(unknown_test)}): {detect_unknown:.4f}")
    print(f"  false-positive rate on benign holdout "
          f"(n={len(benign_test)}): {fpr_benign:.4f}")
    print()
    print(f"artifacts written to {ARTIFACTS} "
          f"in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
