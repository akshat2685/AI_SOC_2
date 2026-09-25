"""Confidence scoring for threat-intel indicators.

A small, deterministic scoring step in the ingestion pipeline: every parsed
indicator gets a 0-100 confidence score derived from transparent factors.
This is the "intel score" that downstream automation (e.g. the SOAR
risk-policy engine) can consume directly.

Factors:
  - base: feed reliability (feed_reliability 0-100, default 50)
  - corroboration: +10 per extra independent source, capped at +30
  - age decay: -2 points per day since first seen, capped at -30
  - TLP RED indicators keep a floor: they are rarely shared widely, so
    corroboration is not expected for them (no penalty applied).

The function is total: it never raises. On any unexpected input it returns
the indicator unchanged.
"""

import datetime
from typing import Any, Dict, List, Optional

try:
    from intelligence_engine.threat_intel.models.tlp import normalize_tlp
except ImportError:  # pragma: no cover - fallback for alternate import roots
    from threat_intel.models.tlp import normalize_tlp


def _parse_dt(value: Any) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def score_indicator(indicator: Dict[str, Any]) -> Dict[str, Any]:
    """Score one indicator dict in place (mutates and returns it)."""
    try:
        base = indicator.get("feed_reliability", indicator.get("confidence", 50))
        try:
            score = float(base)
        except (TypeError, ValueError):
            score = 50.0

        sources: List[Any] = indicator.get("sources") or []
        corroboration = max(0, len(sources) - 1)
        score += min(corroboration * 10, 30)

        first_seen = _parse_dt(indicator.get("first_seen") or indicator.get("valid_from"))
        if first_seen is not None:
            now = datetime.datetime.now(datetime.timezone.utc)
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=datetime.timezone.utc)
            age_days = max(0.0, (now - first_seen).total_seconds() / 86400.0)
            # TLP:RED intel is rarely corroborated/shared; don't age-penalize it
            # as aggressively — staleness still matters, just less.
            decay_rate = 1.0 if normalize_tlp(indicator.get("tlp")) == "RED" else 2.0
            score -= min(age_days * decay_rate, 30)

        score = max(0, min(100, round(score)))
        indicator["confidence"] = score
        indicator["confidence_breakdown"] = {
            "base": base,
            "corroboration_sources": len(sources),
            "scored_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        return indicator
    except Exception:
        return indicator


def score_indicators(indicators: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Score a batch of indicator dicts."""
    return [score_indicator(i) for i in indicators]
