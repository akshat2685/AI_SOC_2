"""AI explainability engine for tracking reasoning steps and decision provenance."""
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class ExplanationDecision:
    """Represents an AI threat classification decision and its underlying chain of reasoning."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decision: str = ""
    confidence: float = 0.0
    reasoning_steps: List[str] = field(default_factory=list)
    alert_data: Dict[str, Any] = field(default_factory=dict)

    def to_human_readable(self) -> str:
        """Format the decision and reasoning chain into a human-readable summary report."""
        steps_formatted = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(self.reasoning_steps))
        return f"""=== AI DECISION EXPLAINABILITY REPORT ===
Decision ID: {self.decision_id}
Classification: {self.decision}
Confidence Score: {self.confidence * 100:.1f}%

Reasoning Steps:
{steps_formatted or "  No explicit steps recorded."}
========================================="""


class ExplainabilityEngine:
    """Generates human-readable reasoning trails and maintains decision logs."""

    def __init__(self):
        self._decisions: Dict[str, ExplanationDecision] = {}

    def create_decision(self) -> ExplanationDecision:
        """Create and register a new empty decision record."""
        dec = ExplanationDecision()
        self._decisions[dec.decision_id] = dec
        return dec

    def explain_threat_classification(
        self,
        alert_data: Dict[str, Any],
        indicators: List[str],
        patterns_matched: List[str],
        confidence: float,
        classification: str,
    ) -> ExplanationDecision:
        """Generate a structured explanation for a threat classification decision."""
        steps = [
            f"Analyzed alert data from source '{alert_data.get('source_system', 'unknown')}' with severity '{alert_data.get('severity', 'unknown')}'.",
            f"Identified {len(indicators)} suspicious indicators of compromise (IOCs): {', '.join(indicators)}.",
            f"Correlated against attack patterns, matching: {', '.join(patterns_matched) if patterns_matched else 'none'}.",
            f"Synthesized evidence to classify threat as '{classification}' with {confidence*100:.1f}% confidence.",
        ]
        
        dec = ExplanationDecision(
            decision=classification,
            confidence=confidence,
            reasoning_steps=steps,
            alert_data=alert_data,
        )
        self._decisions[dec.decision_id] = dec
        return dec

    def get_decision(self, decision_id: str) -> Optional[ExplanationDecision]:
        """Retrieve a stored explanation decision by ID."""
        return self._decisions.get(decision_id)


explainability_engine = ExplainabilityEngine()
