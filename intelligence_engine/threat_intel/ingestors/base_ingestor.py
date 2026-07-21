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
        """Execute the ingestion pipeline."""
        raw_data = self.fetch_data()
        indicators = self.parse_data(raw_data)
        return indicators
