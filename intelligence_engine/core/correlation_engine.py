import time
import asyncio
from typing import List, Dict, Any

class CorrelationEngine:
    def __init__(self):
        self.events_cache = []
        self.lock = asyncio.Lock()
        
    async def add_event(self, event: Dict[str, Any]):
        async with self.lock:
            self.events_cache.append(event)
        
    async def temporal_correlation(self, time_window_seconds: int) -> List[Dict[str, Any]]:
        """Finds events occurring within a specific time window."""
        correlated_alerts = []
        async with self.lock:
            events_snapshot = self.events_cache.copy()
        
        # Sort events by timestamp
        sorted_events = sorted(events_snapshot, key=lambda x: x.get('timestamp', 0))
        
        for i, event1 in enumerate(sorted_events):
            for j in range(i + 1, len(sorted_events)):
                event2 = sorted_events[j]
                time_diff = abs(event2.get('timestamp', 0) - event1.get('timestamp', 0))
                
                if time_diff <= time_window_seconds:
                    if self._is_suspicious_login_and_powershell(event1, event2):
                        correlated_alerts.append({
                            'rule': 'Temporal: Suspicious Login followed by PowerShell execution',
                            'events': [event1, event2],
                            'severity': 'HIGH'
                        })
        return correlated_alerts

    async def graph_based_correlation(self) -> List[Dict[str, Any]]:
        """Correlates events based on shared entities (e.g., user, host)."""
        correlated_alerts = []
        entity_graph = {}
        
        async with self.lock:
            events_snapshot = self.events_cache.copy()
        
        for event in events_snapshot:
            user = event.get('user')
            host = event.get('host')
            
            if user:
                if user not in entity_graph:
                    entity_graph[user] = []
                entity_graph[user].append(event)
                
            if host:
                if host not in entity_graph:
                    entity_graph[host] = []
                entity_graph[host].append(event)

        for entity, events in entity_graph.items():
            if len(events) >= 2:
                # Look for Suspicious Login and PowerShell on same entity
                has_login = any(e.get('action') == 'suspicious_login' for e in events)
                has_ps = any(e.get('action') == 'powershell_execution' for e in events)
                
                if has_login and has_ps:
                    correlated_alerts.append({
                        'rule': f'Graph: Suspicious Login and PowerShell linked to {entity}',
                        'events': events,
                        'severity': 'CRITICAL'
                    })
                    
        return correlated_alerts
        
    def _is_suspicious_login_and_powershell(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> bool:
        actions = {event1.get('action'), event2.get('action')}
        return 'suspicious_login' in actions and 'powershell_execution' in actions
