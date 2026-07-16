import time
import logging
from typing import Dict, Any
from application.services import AlertProcessingService, IEventBus
from infrastructure.event_bus import StubKafkaEventBus

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class BaseWorker:
    def __init__(self, event_bus: IEventBus):
        self.event_bus = event_bus
        
    def start(self) -> None:
        raise NotImplementedError

class SecurityAlertWorker(BaseWorker):
    """
    Background worker that listens to raw security logs on the event bus, 
    delegates processing to the application service, and handles alerts.
    """
    def __init__(self, event_bus: IEventBus, alert_service: AlertProcessingService):
        super().__init__(event_bus)
        self.alert_service = alert_service

    def _handle_raw_log(self, event: Dict[str, Any]) -> None:
        logger.info(f"[Worker] Received raw log: {event}")
        # Zero-trust: Pass through to service which handles validation
        alert_payload = {
            "id": event.get("event_id", "unknown"),
            "severity": event.get("level", "low"),
            "description": event.get("msg", "No description"),
            "source_ip": event.get("src_ip", "0.0.0.0")
        }
        success = self.alert_service.process_alert(alert_payload)
        if not success:
            logger.warning("[Worker] Failed to process alert from raw log - Invalid schema or data.")

    def start(self) -> None:
        logger.info("[Worker] Setting up SecurityAlertWorker subscriptions...")
        self.event_bus.subscribe("raw_security_logs", self._handle_raw_log)
        logger.info("[Worker] SecurityAlertWorker is ready and listening.")

if __name__ == "__main__":
    # Dependency Injection Setup
    bus = StubKafkaEventBus()
    svc = AlertProcessingService(bus)
    worker = SecurityAlertWorker(bus, svc)
    
    worker.start()
    
    # Keep worker alive (simulated)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[Worker] Gracefully shutting down.")
