"""Inference-time loading for the SOC ML models.

Models are trained offline (see train.py) on synthetic SOC telemetry v1.
Every output is labeled with model version + training provenance so a
consumer can never mistake synthetic-trained scores for production-grade ML.
If artifacts are missing, all helpers degrade to None and the API answers 503
on the dedicated endpoints (predict-risk keeps its heuristic).
"""

import json
import math
import os

import joblib
import numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
_ART = os.path.join(_DIR, "artifacts")

MODEL_VERSION = "attack-grounded-v2"
TRAINED_ON = "synthetic-soc-telemetry-v1"
WARNING = "Models trained on synthetic telemetry v1 — retrain on real tenant data before production use."
ZERO_DAY_NOTE = (
    "The anomaly detector is the 0-day signal: it was fit on benign-only traffic and flags "
    "behavioral deviations, not signatures. The classifier only recognizes attack patterns "
    "present in its training data."
)

_cache: dict = {}
_schema_cache: dict | None = None


def _load(name: str):
    if name not in _cache:
        path = os.path.join(_ART, name)
        _cache[name] = joblib.load(path) if os.path.exists(path) else None
    return _cache[name]


def _schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        with open(os.path.join(_ART, "feature_schema.json")) as f:
            _schema_cache = json.load(f)
    return _schema_cache


def models_available() -> bool:
    return all(
        os.path.exists(os.path.join(_ART, n))
        for n in ("triage_clf.pkl", "severity_clf.pkl", "anomaly_iforest.pkl")
    )


def build_vector(features: dict) -> np.ndarray:
    """Build the ordered feature vector. Unknown numerics default to 0."""
    s = _schema()
    asset_type = str(features.get("src_asset_type", "workstation")).lower()
    vec = []
    for col in s["feature_columns"]:
        if col.startswith("asset_"):
            vec.append(1.0 if col == f"asset_{asset_type}" else 0.0)
        else:
            try:
                vec.append(float(features.get(col, 0) or 0))
            except (TypeError, ValueError):
                vec.append(0.0)
    return np.array(vec, dtype=float).reshape(1, -1)


def predict_triage(features: dict) -> dict | None:
    """Supervised: known-attack classification + severity. Returns None if unloaded."""
    clf, sev = _load("triage_clf.pkl"), _load("severity_clf.pkl")
    if clf is None:
        return None
    s = _schema()
    vec = build_vector(features)
    atk_idx = int(clf.predict(vec)[0])
    atk_proba = clf.predict_proba(vec)[0]
    out = {
        "attack_type": s["attack_type_classes"][atk_idx],
        "attack_confidence": round(float(atk_proba[atk_idx]), 3),
    }
    if sev is not None:
        si = int(sev.predict(vec)[0])
        sp = sev.predict_proba(vec)[0]
        out["severity"] = s["severity_classes"][si]
        out["severity_confidence"] = round(float(sp[si]), 3)
    return out


def predict_anomaly(features: dict) -> dict | None:
    """Unsupervised 0-day signal: IsolationForest fit on benign-only traffic."""
    iso = _load("anomaly_iforest.pkl")
    if iso is None:
        return None
    vec = build_vector(features)
    raw = float(iso.decision_function(vec)[0])  # higher = more normal
    anomaly_score = round(1.0 / (1.0 + math.exp(8 * raw)), 3)
    return {"anomaly_score": anomaly_score, "is_anomaly": bool(iso.predict(vec)[0] == -1)}
