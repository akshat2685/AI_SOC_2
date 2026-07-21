import unittest
from plugin import SafetyController, EmulationEngine, RedAgent, SimulationCoordinator

class TestSafetyController(unittest.TestCase):
    def setUp(self):
        self.safety_controller = SafetyController()

    def test_valid_signature_passes(self):
        request = {"signature": "valid_signature_123"}
        self.assertTrue(self.safety_controller.validate_simulation_request(request))

    def test_missing_signature_raises_error(self):
        request = {"no_signature": "here"}
        with self.assertRaises(ValueError) as context:
            self.safety_controller.validate_simulation_request(request)
        self.assertIn("missing valid signature", str(context.exception))

    def test_invalid_request_type_raises_error(self):
        request = "invalid_request_format"
        with self.assertRaises(ValueError) as context:
            self.safety_controller.validate_simulation_request(request)
        self.assertIn("Unauthorized: Simulation request missing valid signature", str(context.exception))

    def test_kill_switch_blocks_emulation(self):
        self.safety_controller.trigger_kill_switch()
        request = {"signature": "valid_signature_123"}
        with self.assertRaises(RuntimeError) as context:
            self.safety_controller.validate_simulation_request(request)
        self.assertIn("Kill-switch is engaged", str(context.exception))

class TestEmulationEngine(unittest.TestCase):
    def test_execute_ttp_valid(self):
        engine = EmulationEngine()
        result = engine.execute_ttp("TTP-123")
        self.assertEqual(result["ttp_id"], "TTP-123")
        self.assertEqual(result["status"], "simulated_execution_completed")

    def test_execute_ttp_invalid(self):
        engine = EmulationEngine()
        with self.assertRaises(ValueError):
            engine.execute_ttp(123)

class TestRedAgent(unittest.TestCase):
    def test_plan_simulation_valid(self):
        agent = RedAgent()
        result = agent.plan_simulation({"os": "linux"})
        self.assertIsInstance(result, list)

    def test_plan_simulation_invalid(self):
        agent = RedAgent()
        with self.assertRaises(ValueError):
            agent.plan_simulation("invalid")

class TestSimulationCoordinator(unittest.TestCase):
    def test_run_exercise_success(self):
        coord = SimulationCoordinator(RedAgent(), SafetyController(), EmulationEngine())
        res = coord.run_exercise({"signature": "valid", "environment": {}})
        self.assertEqual(res["status"], "success")
        self.assertIsInstance(res["results"], list)

    def test_run_exercise_blocked(self):
        safety = SafetyController()
        safety.trigger_kill_switch()
        coord = SimulationCoordinator(RedAgent(), safety, EmulationEngine())
        res = coord.run_exercise({"signature": "valid", "environment": {}})
        self.assertEqual(res["status"], "error")
        self.assertIn("Kill-switch is engaged", res["message"])

if __name__ == '__main__':
    unittest.main()
