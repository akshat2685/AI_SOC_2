"""Automatic gated retrain: close the self-learning loop.

Before this module, training_feedback rows accumulated forever and the
gated retrain (retrain_with_feedback.py) only ran when a human executed
the script by hand — the SOC collected lessons and never applied them.

Now the sparring loop calls maybe_auto_retrain() after every pass:
  - Count training_feedback rows; compare against the total recorded
    by the most recent ml_retrain_runs row.
  - If new rows >= RETRAIN_MIN_NEW_ROWS (env, default 25), run the
    gated retrain OFF the event loop (asyncio.to_thread) via
    app.ml.retrain_service.run_retrain — the same code and the same
    regression gate as the CLI. A worse model never replaces the
    serving one: the gate writes nothing on failure.
  - Persist EVERY attempt to ml_retrain_runs (pass, gate fail, error),
    so GET /ml/models can report the loop's real history. The attempt
    row also advances the baseline, so a failing retrain is retried
    only after another threshold of fresh rows — no CPU hammering.
  - On pass, reload the inference caches in-process so the new model
    serves immediately (inference.reload_models).

Fail-safe by contract: nothing here raises. A retrain problem must
never break the API or the sparring loop that triggered it.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()

DEFAULT_MIN_NEW_ROWS = 25


def min_new_rows() -> int:
    try:
        return max(1, int(os.environ.get(
            "RETRAIN_MIN_NEW_ROWS", str(DEFAULT_MIN_NEW_ROWS))))
    except (TypeError, ValueError):
        return DEFAULT_MIN_NEW_ROWS


def _sync_db_url() -> str | None:
    """Resolve a SYNC SQLAlchemy URL for the retrain's blocking DB read."""
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not url:
        try:
            from app.core.config import settings
            url = getattr(settings, "DATABASE_URL", None) or getattr(
                settings, "POSTGRES_URL", None)
        except Exception:
            url = None
    if not url:
        return None
    # The app runs async drivers; the retrain reads via a sync engine.
    return (url.replace("postgresql+asyncpg://", "postgresql://")
               .replace("sqlite+aiosqlite://", "sqlite://"))


def _run_retrain_sync() -> dict:
    """Blocking: load feedback rows and run the gated retrain.

    Executed via asyncio.to_thread so the API event loop never stalls
    on model training.
    """
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.domain.models import TrainingFeedback
    from app.ml.retrain_service import run_retrain

    url = _sync_db_url()
    if not url:
        raise RuntimeError("no database URL resolvable for auto-retrain")
    engine = create_engine(url)
    try:
        with Session(engine) as s:
            rows = (s.execute(
                select(TrainingFeedback).order_by(TrainingFeedback.id))
                .scalars().all())
            by_source = {}
            for src, cnt in s.execute(
                    select(TrainingFeedback.source, func.count())
                    .group_by(TrainingFeedback.source)).all():
                by_source[src] = int(cnt)
    finally:
        engine.dispose()
    return run_retrain(rows, by_source)


async def feedback_totals(db) -> tuple[int, dict]:
    from sqlalchemy import func, select

    from app.domain.models import TrainingFeedback

    total = (await db.execute(
        select(func.count()).select_from(TrainingFeedback))).scalar_one()
    by_source = {}
    for src, cnt in (await db.execute(
            select(TrainingFeedback.source, func.count())
            .group_by(TrainingFeedback.source))).all():
        by_source[src] = int(cnt)
    return int(total), by_source


async def latest_run(db):
    from sqlalchemy import desc, select

    from app.domain.models import MLRetrainRun

    return (await db.execute(
        select(MLRetrainRun).order_by(desc(MLRetrainRun.id)).limit(1))
    ).scalars().first()


def run_dict(run) -> dict:
    return {
        "id": run.id,
        "trigger": run.trigger,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "feedback_rows_total": run.feedback_rows_total,
        "feedback_rows_new": run.feedback_rows_new,
        "feedback_by_source": run.feedback_by_source or {},
        "model_version_before": run.model_version_before,
        "model_version_after": run.model_version_after,
        "triage_accuracy": run.triage_accuracy,
        "anomaly_fpr": run.anomaly_fpr,
        "gate_failures": run.gate_failures or [],
        "error": run.error,
        "elapsed_seconds": run.elapsed_seconds,
    }


async def retrain_status(db) -> dict:
    """Status block for GET /ml/models: is the loop learning, and when
    did it last actually retrain?"""
    from sqlalchemy import desc, select

    from app.domain.models import MLRetrainRun

    total, by_source = await feedback_totals(db)
    last = await latest_run(db)
    baseline = last.feedback_rows_total if last else 0
    recent = (await db.execute(
        select(MLRetrainRun).order_by(desc(MLRetrainRun.id)).limit(5))
    ).scalars().all()
    return {
        "auto_enabled": True,
        "min_new_rows": min_new_rows(),
        "feedback_rows_total": total,
        "feedback_by_source": by_source,
        "new_rows_since_last_run": total - baseline,
        "last_run": run_dict(last) if last else None,
        "recent_runs": [run_dict(r) for r in recent],
    }


async def maybe_auto_retrain(trigger: str = "sparring_pass", db=None) -> dict:
    """Evaluate the threshold and run the gated retrain if due.

    Returns a small outcome dict. NEVER raises. `db` is injectable for
    tests; production callers omit it and a service-scope session is
    opened (retrain state is global, not tenant-scoped).
    """
    if _lock.locked():
        return {"status": "already_running"}
    async with _lock:
        try:
            if db is not None:
                return await _evaluate_and_run(trigger, db)
            from app.infrastructure.database import service_scope
            async with service_scope() as sdb:
                return await _evaluate_and_run(trigger, sdb)
        except Exception as exc:  # fail-safe: record and swallow
            logger.exception("auto-retrain: evaluation failed")
            await _record_error(trigger, exc, db=db)
            return {"status": "error", "error": str(exc)}


async def _evaluate_and_run(trigger: str, db) -> dict:
    from app.domain.models import MLRetrainRun

    total, by_source = await feedback_totals(db)
    last = await latest_run(db)
    baseline = last.feedback_rows_total if last else 0
    new_rows = total - baseline
    threshold = min_new_rows()
    if new_rows < threshold:
        logger.info(
            "auto-retrain: skipped — %d new feedback rows < threshold %d "
            "(total %d)", new_rows, threshold, total)
        return {"status": "skipped", "reason": "below_threshold",
                "feedback_rows_total": total, "new_rows": new_rows,
                "threshold": threshold}

    logger.info(
        "auto-retrain: %d new feedback rows >= threshold %d — running "
        "gated retrain (trigger=%s)", new_rows, threshold, trigger)
    started = datetime.now(timezone.utc)
    outcome = await asyncio.to_thread(_run_retrain_sync)
    run = MLRetrainRun(
        trigger=trigger,
        status=outcome["status"],
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        feedback_rows_total=total,
        feedback_rows_new=new_rows,
        feedback_by_source=by_source,
        model_version_before=outcome.get("model_version_before"),
        model_version_after=outcome.get("model_version_after"),
        triage_accuracy=outcome.get("triage_accuracy"),
        anomaly_fpr=outcome.get("anomaly_fpr"),
        gate_failures=outcome.get("gate_failures") or [],
        error=None,
        elapsed_seconds=outcome.get("elapsed_seconds"),
    )
    db.add(run)
    await db.commit()
    logger.info("auto-retrain: recorded run #%s status=%s",
                run.id, run.status)

    if outcome["status"] == "passed":
        try:
            from app.ml import inference
            reloaded = inference.reload_models()
            logger.info("auto-retrain: inference reloaded -> %s",
                        reloaded.get("model_version"))
        except Exception:
            logger.exception("auto-retrain: inference reload failed "
                             "(new artifacts serve on next restart)")
    return {"status": outcome["status"], "run_recorded": True,
            "feedback_rows_total": total, "new_rows": new_rows,
            "model_version_after": outcome.get("model_version_after")}


async def _record_error(trigger: str, exc: Exception, db=None) -> None:
    """Best-effort error row so a broken retrain is visible in /ml/models
    and doesn't retry until another threshold of fresh rows arrives."""
    try:
        from app.domain.models import MLRetrainRun

        async def _write(session) -> None:
            total, by_source = await feedback_totals(session)
            now = datetime.now(timezone.utc)
            session.add(MLRetrainRun(
                trigger=trigger, status="error", started_at=now,
                finished_at=now, feedback_rows_total=total,
                feedback_rows_new=0, feedback_by_source=by_source,
                error=str(exc)[:2000]))
            await session.commit()

        if db is not None:
            await _write(db)
        else:
            from app.infrastructure.database import service_scope
            async with service_scope() as sdb:
                await _write(sdb)
    except Exception:
        logger.exception("auto-retrain: could not record error row")
