from typing import Dict, Type
from .base import BaseConnector

class ConnectorRegistry:
    """Registry for dynamically loading and accessing SOAR connectors."""
    _connectors: Dict[str, Type[BaseConnector]] = {}

    @classmethod
    def register(cls, name: str):
        def wrapper(connector_cls: Type[BaseConnector]):
            cls._connectors[name] = connector_cls
            return connector_cls
        return wrapper

    @classmethod
    def get_connector(cls, name: str, tenant_id: int) -> BaseConnector:
        connector_cls = cls._connectors.get(name)
        if not connector_cls:
            raise ValueError(f"Connector '{name}' not found in registry.")
        return connector_cls(tenant_id)
