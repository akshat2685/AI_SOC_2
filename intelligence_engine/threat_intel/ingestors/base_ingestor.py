from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseIngestor(ABC):
    def __init__(self, tenant_id: str, organization_id: str = None):
        self.tenant_id = tenant_id
        self.organization_id = organization_id

    @abstractmethod
    def fetch_data(self) -> List[Dict[str, Any]]:
        """Fetch threat intelligence data from the source."""
        pass

    @abstractmethod
    def parse_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse raw data into standard Indicator format."""
        pass

    def run(self) -> List[Dict[str, Any]]:
        """Execute the ingestion pipeline.

        fetch -> parse -> normalize TLP markings -> confidence scoring.
        The enrichment steps are best-effort: they never break ingestion.
        """
        raw_data = self.fetch_data()
        indicators = self.parse_data(raw_data)
        indicators = self._enrich_indicators(indicators)
        return indicators

    def _enrich_indicators(self, indicators: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize TLP markings and compute confidence scores."""
        try:
            try:
                from intelligence_engine.threat_intel.models.tlp import normalize_tlp
            except ImportError:
                from threat_intel.models.tlp import normalize_tlp
            try:
                from intelligence_engine.threat_intel.processing.scoring import score_indicators
            except ImportError:
                from threat_intel.processing.scoring import score_indicators
        except ImportError:
            return indicators  # enrichment unavailable; return parsed as-is
        for indicator in indicators:
            indicator["tlp"] = normalize_tlp(indicator.get("tlp"))
        return score_indicators(indicators)
