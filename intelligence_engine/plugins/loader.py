import json
import importlib
from pathlib import Path
from typing import Tuple, List, Any
import logging
from .registry import PluginRegistry, PluginInfo
from .manifest import PluginManifest

logger = logging.getLogger(__name__)

def load_plugin(plugin_dir: Path) -> Tuple[PluginInfo, Any]:
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json in {plugin_dir}")
        
    with open(manifest_path, 'r') as f:
        manifest_data = json.load(f)
        
    manifest = PluginManifest(**manifest_data)
    
    module_path = f"intelligence_engine.plugins.{plugin_dir.name}.{manifest.connector_module}"
    module = importlib.import_module(module_path)
    connector_class = getattr(module, manifest.connector_class)
    instance = connector_class()
    
    info = PluginInfo(
        name=manifest.name,
        version=manifest.version,
        author=manifest.author,
        description=manifest.description,
        category=manifest.category,
        capabilities=manifest.capabilities,
        status="INSTALLED"
    )
    
    return info, instance

def discover_plugins(plugins_root: Path) -> List[Path]:
    if not plugins_root.exists():
        return []
    plugins = []
    for d in plugins_root.iterdir():
        if d.is_dir() and (d / "manifest.json").exists():
            plugins.append(d)
    return plugins

def load_all_plugins(plugins_root: Path, registry: PluginRegistry):
    plugins = discover_plugins(plugins_root)
    for p in plugins:
        try:
            info, instance = load_plugin(p)
            registry.register(info, instance)
            logger.info(f"Successfully loaded plugin {info.name}")
        except Exception as e:
            logger.error(f"Failed to load plugin from {p}: {e}")
