"""Sparring data models.

Deliberately plain dataclasses with an in-memory store — NOT SQLAlchemy
models. The twin's findings must never be mistaken for real alerts, and
writing an alembic migration is out of scope for this module (the parent
consolidates migrations). Runs live in-process; a restart clears history.
If durable sparring history is ever needed, these shapes map 1:1 onto a
future sparring_runs / sparring_findings table pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

SIMULATED_MARKER = "digital-twin-simulated"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SparringFinding:
    """One technique (or benign archetype) exercised against the engine."""

    run_id: str
    technique_id: str  # ATT&CK id for attacks; "benign:<archetype>" for FP calibration
    kind: str  # "attack" | "benign"
    detected: bool
    detector: str | None = None  # "rules-v1" | "ml-anomaly-v1"
    rule_id: str | None = None  # e.g. "suspicious-cmdline", "ml-anomaly"
    events_until_detection: int | None = None
    events_total: int = 0
    # Every rule that fired during the ordered pass, in firing order.
    # "detected" mirrors the engine faithfully (any finding counts), but
    # on a fresh virtual device first-seen-binary fires on almost every
    # technique — the breakdown keeps coverage honest about WHAT caught it.
    all_rule_ids: list[str] = field(default_factory=list)
    evasion_features: dict | None = None  # labeled training row when kind=attack and not detected
    simulated: bool = True


@dataclass
class SparringRun:
    """One full sparring pass over a set of techniques + benign archetypes."""

    id: str
    started_at: datetime
    finished_at: datetime | None = None
    technique_count: int = 0
    detected_count: int = 0
    evasion_count: int = 0
    fp_count: int = 0
    benign_count: int = 0
    engine_version: str = "detection-v1"
    model_version: str | None = None
    findings: list[SparringFinding] = field(default_factory=list)
    simulated: bool = True

    @property
    def detection_rate(self) -> float | None:
        if not self.technique_count:
            return None
        return round(self.detected_count / self.technique_count, 3)

    @property
    def duration_s(self) -> float | None:
        if not self.finished_at:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 2)


# ---------------------------------------------------------------------------
# In-memory store. Runs are tenant-agnostic simulations; nothing here touches
# tenant data. Cleared on process restart — see module docstring.
# ---------------------------------------------------------------------------

_RUNS: dict[str, SparringRun] = {}
_EVASION_ROWS: list[dict] = []  # labeled training rows for the retrain pipeline


def store_run(run: SparringRun) -> None:
    _RUNS[run.id] = run


def get_run(run_id: str) -> SparringRun | None:
    return _RUNS.get(run_id)


def list_runs(limit: int = 20) -> list[SparringRun]:
    runs = sorted(_RUNS.values(), key=lambda r: r.started_at, reverse=True)
    return runs[:limit]


def store_evasion_rows(rows: list[dict]) -> None:
    _EVASION_ROWS.extend(rows)


def get_stored_evasion_rows() -> list[dict]:
    return list(_EVASION_ROWS)
