from dataclasses import dataclass
from typing import List, Dict, Tuple, Any
import threading

@dataclass
class PluginInfo:
    name: str
    version: str
    author: str
    description: str
    category: str
    capabilities: List[str]
    status: str

class PluginRegistry:
    def __init__(self):
        self._plugins: Dict[str, Tuple[PluginInfo, Any]] = {}
        self._lock = threading.Lock()
        
    def register(self, info: PluginInfo, instance: Any):
        with self._lock:
            self._plugins[info.name] = (info, instance)
            
    def get(self, name: str) -> Tuple[PluginInfo, Any]:
        with self._lock:
            return self._plugins.get(name)
            
    def list_all(self) -> List[PluginInfo]:
        with self._lock:
            return [info for info, _ in self._plugins.values()]
            
    def list_by_category(self, category: str) -> List[PluginInfo]:
        with self._lock:
            return [info for info, _ in self._plugins.values() if info.category == category]
            
    def unregister(self, name: str):
        with self._lock:
            if name in self._plugins:
                del self._plugins[name]
                
    def update_status(self, name: str, status: str):
        with self._lock:
            if name in self._plugins:
                info, instance = self._plugins[name]
                info.status = status
