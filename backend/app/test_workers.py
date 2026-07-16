import unittest
from application.services import AlertProcessingService
from infrastructure.event_bus import StubKafkaEventBus
from workers import SecurityAlertWorker

class TestWorkerFlow(unittest.TestCase):
    def test_worker_processing(self):
        bus = StubKafkaEventBus()
        svc = AlertProcessingService(bus)
        worker = SecurityAlertWorker(bus, svc)
        
        # Start worker (subscribes to raw_security_logs)
        worker.start()
        
        # We need to capture the output of processed_alerts
        processed_alerts = []
        def capture_processed(msg):
            processed_alerts.append(msg)
            
        bus.subscribe("processed_alerts", capture_processed)
        
        # Publish a raw log
        raw_log = {
            "event_id": "EVT-001",
            "level": "critical",
            "msg": "Unauthorized access attempt",
            "src_ip": "192.168.1.50"
        }
        
        bus.publish("raw_security_logs", raw_log)
        
        self.assertEqual(len(processed_alerts), 1)
        alert = processed_alerts[0]
        self.assertEqual(alert["id"], "EVT-001")
        self.assertEqual(alert["severity"], "critical")
        self.assertTrue(alert["analyzed"])
        self.assertEqual(alert["mitigation_action"], "isolate_host")

if __name__ == '__main__':
    unittest.main()
