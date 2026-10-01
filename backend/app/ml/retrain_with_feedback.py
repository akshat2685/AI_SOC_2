"""Retrain SOC ML models on base data + accumulated feedback rows.

Standalone CLI wrapper over app.ml.retrain_service.run_retrain (the same
gated retrain the automatic trigger runs — see app/ml/auto_retrain.py):

    cd backend/app/ml && python3 retrain_with_feedback.py

Behaviour (unchanged from the original standalone script):
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

Exit codes: 0 = retrain passed (or no feedback rows yet), 1 = gate fail
or missing/unreadable baseline report.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, BACKEND)  # for app.* imports (threat_data imports bare)

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.domain.models import TrainingFeedback
from app.ml.retrain_service import ARTIFACTS, run_retrain


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


def main() -> int:
    engine = create_engine(_db_url())
    with Session(engine) as s:
        fb_rows = (s.execute(
            select(TrainingFeedback).order_by(TrainingFeedback.id))
            .scalars().all())
        src_counts = {}
        for src, cnt in s.execute(
                select(TrainingFeedback.source, func.count())
                .group_by(TrainingFeedback.source)).all():
            src_counts[src] = int(cnt)

    outcome = run_retrain(fb_rows, src_counts, ARTIFACTS)
    status = outcome["status"]

    if status == "no_baseline":
        for f_ in outcome["gate_failures"]:
            print(f"GATE FAIL: {f_}")
        return 1
    if outcome["model_version_before"]:
        print(f"current production: {outcome['model_version_before']}")
    if status == "no_feedback":
        print("no feedback rows in training_feedback -- nothing to learn, "
              "artifacts untouched.")
        return 0
    print(f"feedback rows: {outcome['rows_used']} {outcome['feedback_by_source']}")
    if status == "gate_failed":
        print("GATE FAIL -- writing nothing, existing artifacts untouched:")
        for f_ in outcome["gate_failures"]:
            print(f"  - {f_}")
        return 1

    print("=" * 64)
    print(f"RETRAIN COMPLETE: {outcome['model_version_after']}")
    print(f"  triage acc={outcome['triage_accuracy']:.4f}  "
          f"anomaly FPR={outcome['anomaly_fpr']:.4f}")
    print(f"  artifacts written to {ARTIFACTS} in {outcome['elapsed_seconds']:.1f}s")
    print("DEPLOY NOTE: inference.reload_models() picks the new version up "
          "in-process; a fresh process reads it from feature_schema.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
