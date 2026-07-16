from ...core.observability import trace

class TicketConnector:
    @trace("ticket_create_incident")
    def create_incident(self, title: str, description: str, severity: str = "medium") -> dict:
        """Creates a ticket in the IT Service Management system."""
        return {
            "status": "success", 
            "action": "create_incident", 
            "ticket_id": "INC-001",
            "title": title
        }
