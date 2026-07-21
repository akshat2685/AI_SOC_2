from typing import Dict, Any
from .state import IncidentState

class SupervisorNode:
    def determine_next(self, state: IncidentState) -> Dict[str, Any]:
        """
        Evaluates IncidentState and determines the next node to execute.
        Returns state update with 'next_node'.
        """
        actions_taken = state.get("actions_taken", [])
        
        if "investigation_completed" not in actions_taken:
            return {"next_node": "investigate"}
            
        if state.get("hitl_status") == "Pending":
            # Wait state for Event Bus to resume
            return {"next_node": "wait"}
            
        if "containment_executed" not in actions_taken and "containment_rejected" not in actions_taken:
            return {"next_node": "contain"}
            
        if "notification_sent" not in actions_taken:
            return {"next_node": "notify"}
            
        return {"next_node": "end"}
