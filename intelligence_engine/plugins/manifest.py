from pydantic import BaseModel
from typing import List, Dict, Any

class PluginManifest(BaseModel):
    name: str
    version: str
    author: str
    description: str
    category: str  # SIEM, EDR, NETWORK, IDENTITY, CLOUD, EMAIL
    connector_module: str  # e.g. 'connector'
    connector_class: str  # e.g. 'WazuhConnector'
    capabilities: List[str]  # e.g. ['fetch_events', 'normalize']
    config_schema: Dict[str, Any] = {}  # JSON Schema for connector config
    min_platform_version: str = '1.0.0'
