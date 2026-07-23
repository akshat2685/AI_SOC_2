import time
import structlog
from typing import Dict, Any
from application.services import AlertProcessingService, IEventBus
from infrastructure.event_bus import StubKafkaEventBus

logger = structlog.get_logger(__name__)

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
        logger.info("raw_log_received", event_id=event.get("event_id"))
        # Zero-trust: Pass through to service which handles validation
        alert_payload = {
            "id": event.get("event_id", "unknown"),
            "severity": event.get("level", "low"),
            "description": event.get("msg", "No description"),
            "source_ip": event.get("src_ip", "0.0.0.0")
        }
        success = self.alert_service.process_alert(alert_payload)
        if not success:
            logger.warning("alert_processing_failed", reason="invalid_schema_or_data")

    def start(self) -> None:
        logger.info("security_alert_worker_start")
        self.event_bus.subscribe("raw_security_logs", self._handle_raw_log)
        logger.info("security_alert_worker_ready")

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
        logger.info("worker_shutdown")
