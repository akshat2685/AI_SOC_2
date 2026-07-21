import logging
from typing import List, Dict, Any
from taxii2client.v21 import Collection
import stix2

try:
    from intelligence_engine.threat_intel.ingestors.base_ingestor import BaseIngestor
except ImportError:
    from .base_ingestor import BaseIngestor

logger = logging.getLogger(__name__)

class TAXIIIngestor(BaseIngestor):
    def __init__(self, tenant_id: str, collection_url: str, username: str = None, password: str = None, organization_id: str = None):
        super().__init__(tenant_id, organization_id)
        self.collection_url = collection_url
        self.username = username
        self.password = password
        
        self.collection = Collection(self.collection_url, user=self.username, password=self.password)

    def fetch_data(self) -> List[Dict[str, Any]]:
        logger.info(f"Fetching data from TAXII {self.collection_url} for tenant {self.tenant_id}")
        try:
            bundle = self.collection.get_objects()
            return bundle.get("objects", [])
        except Exception as e:
            logger.error(f"Error fetching from TAXII: {e}")
            return []

    def parse_data(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        indicators = []
        for obj in raw_data:
            try:
                # Validate standard OASIS STIX 2.1 formatting
                stix_obj = stix2.parse(obj)
                
                if stix_obj.get("type") == "indicator":
                    indicators.append({
                        "feed_id": f"taxii_{self.collection.id}",
                        "indicator_type": stix_obj.get("pattern_type"),
                        "indicator_value": stix_obj.get("pattern"),
                        "raw_data": obj,
                        "tenant_id": self.tenant_id,
                        "organization_id": self.organization_id,
                        "valid_from": str(stix_obj.get("valid_from")) if stix_obj.get("valid_from") else None,
                        "valid_until": str(stix_obj.get("valid_until")) if stix_obj.get("valid_until") else None,
                    })
            except Exception as e:
                logger.error(f"Error parsing STIX object: {e}")
        return indicators
