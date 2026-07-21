from typing import TypedDict, List, Dict, Any, Optional

class IncidentState(TypedDict):
    incident_id: str
    alert_data: Dict[str, Any]
    context: Dict[str, Any]
    playbook_name: str
    actions_taken: List[str]
    hitl_status: Optional[str] # e.g., Pending, Approved, Rejected, None
    next_node: Optional[str] # For routing
