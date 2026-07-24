"""
Agent golden-trace / snapshot tests.

Pins the decision output of the LangGraph-backed `PlaybookRecommender` to a
committed golden snapshot so that any behavioural regression in the agent's
recommendation logic (ranking, confidence, degraded handling, output contract)
is caught in CI.

Snapshots live in `tests/golden/*.json`. To regenerate after an intentional
behaviour change, run:  GOLDEN_UPDATE=1 python -m pytest tests/unit/test_agent_golden_trace.py
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

from intelligence_engine.soar.ai.recommender import PlaybookRecommender

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"


def _assert_matches_golden(name: str, actual: Dict[str, Any]) -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    if os.getenv("GOLDEN_UPDATE") == "1":
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
        pytest.skip(f"golden snapshot {name} regenerated")
    assert path.exists(), f"missing golden snapshot {path} — run with GOLDEN_UPDATE=1"
    expected = json.loads(path.read_text())
    assert actual == expected, f"agent trace drifted from golden snapshot {name}"


class _FakeHit:
    def __init__(self, hit_id: str, score: float, payload: Dict[str, Any]):
        self.id = hit_id
        self.score = score
        self.payload = payload


class _FakeQdrant:
    """Deterministic vector-store stub returning a fixed ranked result set."""

    def __init__(self, hits: List[_FakeHit]):
        self._hits = hits

    async def search(self, *args, **kwargs) -> List[_FakeHit]:
        return self._hits


def _recommender_with(hits: List[_FakeHit], monkeypatch) -> PlaybookRecommender:
    rec = PlaybookRecommender(qdrant_client=_FakeQdrant(hits))
    # Bypass the real sentence-transformers embedding to keep the trace deterministic
    # and free of heavy model downloads on every CI platform.
    async def _fake_embed(_text: str):
        return [0.0, 0.1, 0.2]

    monkeypatch.setattr(rec, "_embed", _fake_embed)
    return rec


@pytest.mark.asyncio
async def test_recommendation_matches_golden(monkeypatch):
    hits = [
        _FakeHit("case-1", 0.97, {"playbook_id": "pb_isolate_host_01", "resolution": "isolated host"}),
        _FakeHit("case-2", 0.71, {"playbook_id": "pb_generic_triage_01", "resolution": "manual triage"}),
    ]
    rec = _recommender_with(hits, monkeypatch)
    result = await rec.get_recommendation({"description": "Suspicious login from 10.0.0.5"})
    _assert_matches_golden("recommender_isolate_host", result)


@pytest.mark.asyncio
async def test_degraded_recommendation_matches_golden(monkeypatch):
    rec = _recommender_with([], monkeypatch)  # empty vector store → degraded path
    result = await rec.get_recommendation({"description": "Unknown anomaly"})
    _assert_matches_golden("recommender_degraded", result)
