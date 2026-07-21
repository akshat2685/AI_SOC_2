from typing import Dict, Any
from .state import IncidentState
from .interfaces import IActionNode

class InvestigationNode(IActionNode):
    def execute(self, state: IncidentState) -> Dict[str, Any]:
        # Gather context about the threat
        # Add to context in state
        context = state.get("context", {})
        context["investigation_details"] = "Gathered initial threat intelligence"
        actions_taken = state.get("actions_taken", []) + ["investigation_completed"]
        
        return {
            "context": context,
            "actions_taken": actions_taken
        }

class ContainmentNode(IActionNode):
    def execute(self, state: IncidentState) -> Dict[str, Any]:
        hitl_status = state.get("hitl_status")
        
        if hitl_status == "Approved":
            actions_taken = state.get("actions_taken", []) + ["containment_executed"]
            return {
                "actions_taken": actions_taken,
                "hitl_status": "Completed"
            }
        elif hitl_status == "Rejected":
            actions_taken = state.get("actions_taken", []) + ["containment_rejected"]
            return {
                "actions_taken": actions_taken,
                "hitl_status": "Completed"
            }
        else:
            # Requires HITL approval
            actions_taken = state.get("actions_taken", []) + ["containment_pending_hitl"]
            return {
                "actions_taken": actions_taken,
                "hitl_status": "Pending"
            }

class NotificationNode(IActionNode):
    def execute(self, state: IncidentState) -> Dict[str, Any]:
        actions_taken = state.get("actions_taken", []) + ["notification_sent"]
        return {
            "actions_taken": actions_taken
        }
