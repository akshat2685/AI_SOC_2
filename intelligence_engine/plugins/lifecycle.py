import logging
from typing import Dict, Any
from .registry import PluginRegistry

logger = logging.getLogger(__name__)

class PluginLifecycleManager:
    def __init__(self, registry: PluginRegistry):
        self.registry = registry
        
    def activate(self, name: str):
        plugin_tuple = self.registry.get(name)
        if not plugin_tuple:
            return
        info, instance = plugin_tuple
        try:
            if hasattr(instance, "connect"):
                instance.connect()
            if hasattr(instance, "authenticate"):
                instance.authenticate()
            self.registry.update_status(name, "ACTIVE")
            logger.info(f"Activated plugin {name}")
        except Exception as e:
            self.registry.update_status(name, "ERROR")
            logger.error(f"Error activating plugin {name}: {e}")
            
    def deactivate(self, name: str):
        plugin_tuple = self.registry.get(name)
        if not plugin_tuple:
            return
        info, instance = plugin_tuple
        try:
            if hasattr(instance, "disconnect"):
                instance.disconnect()
            self.registry.update_status(name, "DISABLED")
            logger.info(f"Deactivated plugin {name}")
        except Exception as e:
            logger.error(f"Error deactivating plugin {name}: {e}")
            
    def health_check(self, name: str) -> Dict[str, Any]:
        plugin_tuple = self.registry.get(name)
        if not plugin_tuple:
            return {"status": "NOT_FOUND"}
        info, instance = plugin_tuple
        if hasattr(instance, "health"):
            return instance.health()
        return {"status": "UNKNOWN"}
        
    def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        results = {}
        for info in self.registry.list_all():
            if info.status == "ACTIVE":
                results[info.name] = self.health_check(info.name)
        return results
        
    def reconnect(self, name: str):
        self.deactivate(name)
        self.activate(name)
