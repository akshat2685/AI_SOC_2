import structlog
from typing import Dict, Any

logger = structlog.get_logger(__name__)

class PostureCalculator:
    """
    Aggregates vulnerability, exposure, and historical data into tenant organizational 
    posture scores and quantifiable dollar-value business impact.
    """
    def __init__(self):
        pass

    def calculate_posture(self, tenant_id: int, vulnerabilities: int, exposure_rate: float, incidents: int) -> Dict[str, Any]:
        """
        Calculates organizational posture score (0-100) and business impact value.
        """
        score = 100.0
        
        score -= min(vulnerabilities * 0.5, 30.0)
        score -= (exposure_rate * 40.0)
        score -= min(incidents * 2.0, 30.0)
        score = max(score, 0.0)
        
        base_value = 5_000_000  # $5M assumed baseline enterprise value
        impact_dollar = base_value * exposure_rate * (max(vulnerabilities, 1) / 100.0)
        
        return {
            "tenant_id": tenant_id,
            "posture_score": round(score, 2),
            "financial_impact_at_risk": round(impact_dollar, 2)
        }
