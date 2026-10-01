"""Auto-retrain: the self-learning loop must close without a human.

Covers:
  - retrain_service gate semantics (no baseline / no feedback / gate
    pass writes artifacts / gate fail writes NOTHING),
  - the threshold trigger (below -> skipped, due -> runs + records +
    baseline advances),
  - retrain_status reporting shape,
  - GET /ml/models carries the retraining block.
"""

import json

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.domain.models import MLRetrainRun, TrainingFeedback
from app.ml import auto_retrain, retrain_service
from app.ml.threat_data import FEATURE_COLUMNS


# ---------- helpers ----------

def _feedback_row(label="attack", source="sparring"):
    return TrainingFeedback(
        tenant_id=1,
        feature_vector={c: 0.5 for c in FEATURE_COLUMNS},
        label=label,
        technique_id="T1059.001" if label == "attack" else None,
        tactic="execution" if label == "attack" else "benign",
        severity="HIGH",
        source=source,
    )


def _col_scales():
    # Per-feature scales: real telemetry features live on wildly
    # different ranges (hour 0-23, MB in the hundreds, entropy 0-8).
    # Uniform-valued features give IsolationForest nothing to model.
    return np.linspace(0.5, 40.0, len(FEATURE_COLUMNS))


def _fake_base_df(n_benign=400, n_attack=400):
    """Strongly separable stand-in for threat_data.generate()."""
    rng = np.random.RandomState(7)
    scales = _col_scales()
    rows = []
    for i in range(n_benign):
        vals = scales * (0.85 + 0.3 * rng.rand(len(FEATURE_COLUMNS)))
        rec = {c: float(v) for c, v in zip(FEATURE_COLUMNS, vals)}
        rec.update(is_attack=0, severity="LOW", technique_id="benign",
                   tactic="benign", provenance="synthetic", archetype="office")
        rows.append(rec)
    for i in range(n_attack):
        vals = scales * (6.0 + rng.rand(len(FEATURE_COLUMNS)))
        rec = {c: float(v) for c, v in zip(FEATURE_COLUMNS, vals)}
        rec.update(is_attack=1, severity="HIGH",
                   technique_id="unknown" if i % 3 == 0 else "T1059.001",
                   tactic="execution", provenance="synthetic",
                   archetype="server")
        rows.append(rec)
    return pd.DataFrame(rows)


def _fake_base_df_noisy(n_benign=200, n_attack=200):
    """Non-separable data: both classes drawn from the SAME distribution,
    so no classifier can reach a 0.98 accuracy gate — the accuracy arm
    of the gate must fail."""
    rng = np.random.RandomState(11)
    scales = _col_scales()
    rows = []
    for i in range(n_benign + n_attack):
        vals = scales * (0.85 + 0.3 * rng.rand(len(FEATURE_COLUMNS)))
        rec = {c: float(v) for c, v in zip(FEATURE_COLUMNS, vals)}
        is_attack = 1 if i >= n_benign else 0
        rec.update(is_attack=is_attack,
                   severity="HIGH" if is_attack else "LOW",
                   technique_id="T1059.001" if is_attack else "benign",
                   tactic="execution" if is_attack else "benign",
                   provenance="synthetic", archetype="office")
        rows.append(rec)
    return pd.DataFrame(rows)


def _write_baseline(artifacts_dir, acc=0.90, fpr=0.05):
    report = {
        "model_version": "attack-grounded-v3",
        "models": {
            "triage_clf": {"accuracy": acc},
            "anomaly_iforest": {"false_positive_rate_benign_holdout": fpr},
        },
    }
    (artifacts_dir / "training_report.json").write_text(json.dumps(report))
    return report


# ---------- retrain_service gate semantics ----------

def test_retrain_no_baseline_writes_nothing(tmp_path):
    outcome = retrain_service.run_retrain([_feedback_row()], {}, str(tmp_path))
    assert outcome["status"] == "no_baseline"
    assert list(tmp_path.iterdir()) == []


def test_retrain_no_feedback(tmp_path):
    _write_baseline(tmp_path)
    outcome = retrain_service.run_retrain([], {}, str(tmp_path))
    assert outcome["status"] == "no_feedback"
    assert outcome["rows_used"] == 0
    assert not (tmp_path / "triage_clf.pkl").exists()


def test_retrain_gate_pass_writes_artifacts(tmp_path, monkeypatch):
    _write_baseline(tmp_path, acc=0.90, fpr=0.20)
    monkeypatch.setattr(retrain_service.train, "generate", _fake_base_df)
    rows = [_feedback_row() for _ in range(5)]
    outcome = retrain_service.run_retrain(rows, {"sparring": 5}, str(tmp_path))
    assert outcome["status"] == "passed", outcome
    assert outcome["model_version_before"] == "attack-grounded-v3"
    assert outcome["model_version_after"] == "attack-grounded-v4+feedback-5"
    assert outcome["triage_accuracy"] >= 0.88  # gate floor: 0.90 - 0.02
    for name in ("triage_clf.pkl", "severity_clf.pkl", "anomaly_iforest.pkl",
                 "feature_schema.json", "training_report.json"):
        assert (tmp_path / name).exists(), name
    report = json.loads((tmp_path / "training_report.json").read_text())
    assert report["model_version"] == "attack-grounded-v4+feedback-5"
    assert report["gate"]["result"] == "PASS"
    assert report["n_feedback_rows"] == 5


def test_retrain_gate_fail_writes_nothing(tmp_path, monkeypatch):
    # Impossible baseline: perfect current accuracy (gate floor 0.98)
    # against non-separable data — the candidate cannot reach it.
    baseline = _write_baseline(tmp_path, acc=1.0, fpr=0.05)
    before = (tmp_path / "training_report.json").read_text()
    monkeypatch.setattr(retrain_service.train, "generate",
                        _fake_base_df_noisy)
    outcome = retrain_service.run_retrain(
        [_feedback_row() for _ in range(5)], {"sparring": 5}, str(tmp_path))
    assert outcome["status"] == "gate_failed"
    assert outcome["gate_failures"]
    assert not (tmp_path / "triage_clf.pkl").exists()
    assert (tmp_path / "training_report.json").read_text() == before
    assert baseline["model_version"] == "attack-grounded-v3"


# ---------- auto-retrain trigger ----------

async def _add_feedback(session, n, source="sparring"):
    for _ in range(n):
        session.add(_feedback_row(source=source))
    await session.commit()


@pytest.fixture
def _fast_threshold(monkeypatch):
    monkeypatch.setenv("RETRAIN_MIN_NEW_ROWS", "3")


async def test_auto_retrain_below_threshold_skips(
        test_db_session, _fast_threshold):
    await _add_feedback(test_db_session, 2)
    outcome = await auto_retrain.maybe_auto_retrain(
        trigger="test", db=test_db_session)
    assert outcome["status"] == "skipped"
    runs = (await test_db_session.execute(
        select(MLRetrainRun))).scalars().all()
    assert runs == []


async def test_auto_retrain_runs_records_and_advances_baseline(
        test_db_session, _fast_threshold, monkeypatch):
    canned = {
        "status": "passed", "rows_used": 5,
        "feedback_by_source": {"sparring": 5},
        "model_version_before": "attack-grounded-v3",
        "model_version_after": "attack-grounded-v4+feedback-5",
        "triage_accuracy": 0.99, "anomaly_fpr": 0.03,
        "gate_failures": [], "elapsed_seconds": 1.5,
    }
    monkeypatch.setattr(auto_retrain, "_run_retrain_sync", lambda: canned)
    # inference.reload_models would read the real artifacts dir; stub it
    # so the test never touches production model files.
    import app.ml.inference as inference
    monkeypatch.setattr(inference, "reload_models",
                        lambda: {"reloaded": True, "model_version": "x"})

    await _add_feedback(test_db_session, 5)
    outcome = await auto_retrain.maybe_auto_retrain(
        trigger="test", db=test_db_session)
    assert outcome["status"] == "passed"

    runs = (await test_db_session.execute(
        select(MLRetrainRun))).scalars().all()
    assert len(runs) == 1
    run = runs[0]
    assert run.status == "passed"
    assert run.trigger == "test"
    assert run.feedback_rows_total == 5
    assert run.feedback_rows_new == 5
    assert run.model_version_after == "attack-grounded-v4+feedback-5"

    # Baseline advanced: with no new rows, the next evaluation skips
    # even though 5 rows exist in total.
    outcome2 = await auto_retrain.maybe_auto_retrain(
        trigger="test", db=test_db_session)
    assert outcome2["status"] == "skipped"
    assert outcome2["new_rows"] == 0


async def test_auto_retrain_records_gate_failure(
        test_db_session, _fast_threshold, monkeypatch):
    canned = {
        "status": "gate_failed", "rows_used": 3,
        "feedback_by_source": {"sparring": 3},
        "model_version_before": "attack-grounded-v3",
        "model_version_after": None,
        "triage_accuracy": 0.50, "anomaly_fpr": 0.40,
        "gate_failures": ["triage accuracy regressed"],
        "elapsed_seconds": 1.0,
    }
    monkeypatch.setattr(auto_retrain, "_run_retrain_sync", lambda: canned)
    await _add_feedback(test_db_session, 3)
    outcome = await auto_retrain.maybe_auto_retrain(
        trigger="test", db=test_db_session)
    assert outcome["status"] == "gate_failed"
    run = (await test_db_session.execute(
        select(MLRetrainRun))).scalars().one()
    assert run.status == "gate_failed"
    assert run.gate_failures == ["triage accuracy regressed"]
    assert run.model_version_after is None


async def test_auto_retrain_never_raises_on_retrain_error(
        test_db_session, _fast_threshold, monkeypatch):
    def _boom():
        raise RuntimeError("training exploded")
    monkeypatch.setattr(auto_retrain, "_run_retrain_sync", _boom)
    await _add_feedback(test_db_session, 4)
    outcome = await auto_retrain.maybe_auto_retrain(
        trigger="test", db=test_db_session)
    assert outcome["status"] == "error"
    run = (await test_db_session.execute(
        select(MLRetrainRun))).scalars().one()
    assert run.status == "error"
    assert "training exploded" in (run.error or "")


# ---------- reporting ----------

async def test_retrain_status_shape(test_db_session, _fast_threshold):
    await _add_feedback(test_db_session, 4)
    test_db_session.add(MLRetrainRun(
        trigger="sparring_pass", status="passed", feedback_rows_total=3,
        feedback_rows_new=3, feedback_by_source={"sparring": 3},
        model_version_before="attack-grounded-v3",
        model_version_after="attack-grounded-v4+feedback-3"))
    await test_db_session.commit()
    status = await auto_retrain.retrain_status(test_db_session)
    assert status["auto_enabled"] is True
    assert status["min_new_rows"] == 3
    assert status["feedback_rows_total"] == 4
    assert status["new_rows_since_last_run"] == 1
    assert status["last_run"]["status"] == "passed"
    assert status["last_run"]["model_version_after"] == \
        "attack-grounded-v4+feedback-3"
    assert len(status["recent_runs"]) == 1


async def test_ml_models_endpoint_reports_retraining(async_client):
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"username": "retrain.tester@example.com",
              "password": "test-password-123"})
    assert reg.status_code in (200, 201), reg.text
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "retrain.tester@example.com",
              "password": "test-password-123"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    res = await async_client.get(
        "/api/v1/ml/models", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["model_version"]
    assert "retraining" in body
