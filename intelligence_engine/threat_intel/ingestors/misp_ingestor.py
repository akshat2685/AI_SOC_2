import logging
from typing import List, Dict, Any
from pymisp import ExpandedPyMISP

try:
    from intelligence_engine.threat_intel.ingestors.base_ingestor import BaseIngestor
except ImportError:
    from .base_ingestor import BaseIngestor

logger = logging.getLogger(__name__)

class MISPIngestor(BaseIngestor):
    def __init__(self, tenant_id: str, url: str, key: str, verifycert: bool = True, organization_id: str = None):
        super().__init__(tenant_id, organization_id)
        self.url = url
        self.key = key
        self.verifycert = verifycert
        self.misp = ExpandedPyMISP(self.url, self.key, self.verifycert)

    def fetch_data(self) -> List[Dict[str, Any]]:
        logger.info(f"Fetching data from MISP {self.url} for tenant {self.tenant_id}")
        try:
            # For demonstration, fetch recent events
            events = self.misp.search(controller='events', return_format='json', limit=50)
            return events if isinstance(events, list) else []
        except Exception as e:
            logger.error(f"Error fetching from MISP: {e}")
            return []

    def parse_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        indicators = []
        for event in raw_data:
            event_info = event.get('Event', {})
            event_id = event_info.get('id')
            attributes = event_info.get('Attribute', [])
            
            for attr in attributes:
                indicators.append({
                    "feed_id": f"misp_{event_id}",
                    "indicator_type": attr.get('type'),
                    "indicator_value": attr.get('value'),
                    "raw_data": attr,
                    "tenant_id": self.tenant_id,
                    "organization_id": self.organization_id
                })
                
        return indicators
