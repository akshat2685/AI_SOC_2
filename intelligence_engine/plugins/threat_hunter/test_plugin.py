import unittest
from plugin import ResourceMonitor, TelemetryCollector, HypothesisEngineClient, BlueAgent

class TestResourceMonitor(unittest.TestCase):
    def test_check_limits(self):
        # Should not raise exception
        ResourceMonitor.check_limits()

class TestTelemetryCollector(unittest.TestCase):
    def test_collect(self):
        collector = TelemetryCollector()
        res = collector.collect()
        self.assertEqual(res["status"], "success")
        self.assertIn("source", res)

class TestHypothesisEngineClient(unittest.TestCase):
    def test_send_telemetry_valid(self):
        client = HypothesisEngineClient()
        self.assertTrue(client.send_telemetry({"status": "ok"}))

    def test_send_telemetry_invalid(self):
        client = HypothesisEngineClient()
        with self.assertRaises(ValueError):
            client.send_telemetry("invalid")
        with self.assertRaises(ValueError):
            client.send_telemetry({"no_status": "ok"})

class TestBlueAgent(unittest.TestCase):
    def test_generate_hypothesis_valid(self):
        agent = BlueAgent()
        res = agent.generate_hypothesis({"threat": "high"})
        self.assertIsInstance(res, str)

    def test_generate_hypothesis_invalid(self):
        agent = BlueAgent()
        with self.assertRaises(ValueError):
            agent.generate_hypothesis("invalid")

if __name__ == '__main__':
    unittest.main()
