import re
import yaml
import logging
from datetime import datetime
import uuid
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)

try:
    from intelligence_engine.connectors.base import SecurityEvent
except ImportError:
    from pydantic import BaseModel
    class SecurityEvent(BaseModel):
        event_id: str
        tenant_id: str
        source: str
        event_type: str
        severity: str
        timestamp: datetime
        raw_payload: dict
        normalized_payload: dict
        iocs: list[str] = []
        mitre_techniques: list[str] = []
        topic: Optional[str] = None

class EventRouter:
    """Topic-based and content-based Event Routing logic."""
    def __init__(self):
        self.routes = []

    def add_route(self, condition: Callable[[SecurityEvent], bool], target_topic: str):
        self.routes.append((condition, target_topic))

    def route_event(self, event: SecurityEvent) -> str:
        for condition, topic in self.routes:
            if condition(event):
                event.topic = topic
                return topic
        event.topic = "default_topic"
        return "default_topic"

class NormalizationEngine:
    """Map raw events to SecurityEvent models with source-specific parsers and a YAML-configurable field mapping engine."""
    def __init__(self, yaml_config_path: str = None, yaml_config_str: str = None):
        self.parsers = {}
        self.field_mappings = {}
        
        if yaml_config_path:
            with open(yaml_config_path, 'r') as f:
                config = yaml.safe_load(f)
                self._load_config(config)
        elif yaml_config_str:
            config = yaml.safe_load(yaml_config_str)
            self._load_config(config)

    def _load_config(self, config: dict):
        if config and 'mappings' in config:
            self.field_mappings = config['mappings']
            
    def register_parser(self, source: str, parser_func: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.parsers[source] = parser_func

    def apply_yaml_mapping(self, raw_event: dict, source: str) -> dict:
        normalized = {}
        source_mapping = self.field_mappings.get(source, {})
        if not source_mapping:
            return raw_event.copy()

        for norm_field, raw_field in source_mapping.items():
            if '.' in raw_field:
                parts = raw_field.split('.')
                val = raw_event
                for part in parts:
                    if isinstance(val, dict):
                        val = val.get(part)
                    else:
                        val = None
                        break
                normalized[norm_field] = val
            else:
                normalized[norm_field] = raw_event.get(raw_field)
        return normalized

    def normalize(self, raw_event: Dict[str, Any], source: str) -> SecurityEvent:
        event_str = str(raw_event)
        iocs = self._extract_iocs(event_str)
        
        # 1. Source-specific parsing
        if source in self.parsers:
            parsed_event = self.parsers[source](raw_event)
        else:
            parsed_event = raw_event
            
        # 2. YAML-configurable field mapping
        normalized_payload = self.apply_yaml_mapping(parsed_event, source)

        event_type = normalized_payload.get('event_type') or parsed_event.get('event_type') or 'unknown'
        severity = normalized_payload.get('severity') or parsed_event.get('severity') or 'LOW'
        
        ts_val = normalized_payload.get('timestamp') or parsed_event.get('timestamp')
        if isinstance(ts_val, str):
            try:
                timestamp = datetime.fromisoformat(ts_val.replace('Z', '+00:00'))
            except ValueError:
                timestamp = datetime.utcnow()
        elif isinstance(ts_val, datetime):
            timestamp = ts_val
        else:
            timestamp = datetime.utcnow()

        event = SecurityEvent(
            event_id=parsed_event.get('id', str(uuid.uuid4())),
            tenant_id=parsed_event.get('tenant_id', 'default'),
            source=source,
            event_type=event_type,
            severity=severity,
            timestamp=timestamp,
            raw_payload=raw_event,
            normalized_payload=normalized_payload,
            iocs=iocs,
            mitre_techniques=self._map_mitre(event_type)
        )
        return event

    def _extract_iocs(self, text: str) -> list[str]:
        iocs = []
        # IPv4
        ips = re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', text)
        for ip in ips:
            if not ip.startswith('10.') and not ip.startswith('192.168.') and not re.match(r'^172\.(1[6-9]|2[0-9]|3[0-1])\.', ip) and ip != '127.0.0.1':
                iocs.append(ip)
        # MD5/SHA
        hashes = re.findall(r'\b[a-fA-F0-9]{32,64}\b', text)
        iocs.extend(hashes)
        return list(set(iocs))

    def _map_mitre(self, event_type: str) -> list[str]:
        mapping = {
            'login_failed': ['T1110'],
            'process_creation': ['T1059'],
            'network_connection': ['T1071']
        }
        return mapping.get(event_type, [])

default_engine = NormalizationEngine()
default_router = EventRouter()

# Setup default routes
default_router.add_route(lambda e: e.severity.upper() == 'CRITICAL', 'critical_alerts')
default_router.add_route(lambda e: e.event_type == 'login_failed', 'auth_events')
default_router.add_route(lambda e: 'T1059' in e.mitre_techniques, 'process_events')

def normalize_event(raw_event: Dict[str, Any], source: str) -> SecurityEvent:
    event = default_engine.normalize(raw_event, source)
    default_router.route_event(event)
    return event
