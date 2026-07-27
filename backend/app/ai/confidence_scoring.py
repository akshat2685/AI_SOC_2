"""Threat detection confidence scoring and auto-execution threshold calculation module."""
from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class ConfidenceScore:
    """Represents a multi-factor confidence assessment for threat detection."""
    overall: float
    indicator_count: int = 0
    pattern_ratio: float = 0.0
    asset_criticality: float = 0.0
    historical_fp_rate: float = 0.0


class ConfidenceScorer:
    """Calculates confidence scores and evaluates autonomous action thresholds."""

    AUTO_EXECUTE_THRESHOLD = 0.85

    def score_threat_detection(
        self,
        indicators: List[str],
        pattern_matches: int,
        total_patterns_checked: int,
        asset_criticality: float,
        historical_fp_rate: float,
    ) -> ConfidenceScore:
        """Calculate a composite confidence score bounded between 0.0 and 1.0."""
        indicator_count = len(indicators) if indicators else 0
        pattern_ratio = (pattern_matches / total_patterns_checked) if total_patterns_checked > 0 else 0.0
        
        # Weighted score formula
        raw_score = (
            min(1.0, indicator_count * 0.15) * 0.3 +
            pattern_ratio * 0.3 +
            asset_criticality * 0.2 +
            (1.0 - min(1.0, historical_fp_rate)) * 0.2
        )
        
        overall = max(0.01, min(1.0, raw_score))
        return ConfidenceScore(
            overall=overall,
            indicator_count=indicator_count,
            pattern_ratio=pattern_ratio,
            asset_criticality=asset_criticality,
            historical_fp_rate=historical_fp_rate,
        )

    def can_auto_execute(self, action: str, score: ConfidenceScore) -> Tuple[bool, str]:
        """Determine if a threat response action can be executed autonomously without human intervention."""
        if score.overall >= self.AUTO_EXECUTE_THRESHOLD:
            return True, f"Confidence score {score.overall:.2f} meets auto-execute threshold ({self.AUTO_EXECUTE_THRESHOLD})"
        return False, f"Action '{action}' requires human approval: confidence {score.overall:.2f} is below threshold ({self.AUTO_EXECUTE_THRESHOLD})"


confidence_scorer = ConfidenceScorer()
