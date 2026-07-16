import abc
from typing import Dict, Any
from pydantic import BaseModel, ValidationError

class IEventBus(abc.ABC):
    @abc.abstractmethod
    def publish(self, topic: str, message: Dict[str, Any]) -> None:
        pass

    @abc.abstractmethod
    def subscribe(self, topic: str, handler: Any) -> None:
        pass

class Alert(BaseModel):
    id: str
    severity: str
    description: str
    source_ip: str
    
class IAlertService(abc.ABC):
    @abc.abstractmethod
    def process_alert(self, alert_data: Dict[str, Any]) -> bool:
        pass

class AlertProcessingService(IAlertService):
    def __init__(self, event_bus: IEventBus) -> None:
        self.event_bus = event_bus

    def process_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Processes incoming alert data, validates, and publishes it."""
        try:
            # Validate payload using Pydantic (Zero-trust approach)
            alert = Alert(**alert_data)
        except ValidationError:
            # In a real SOC, log this as a potential tampering attempt or invalid data
            return False
            
        # Enrich or analyze here...
        enriched_data = alert.model_dump()
        enriched_data["analyzed"] = True
        enriched_data["mitigation_action"] = "isolate_host" if alert.severity == "critical" else "log"
        
        self.event_bus.publish("processed_alerts", enriched_data)
        return True
