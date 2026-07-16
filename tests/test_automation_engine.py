import unittest
from unittest.mock import patch, MagicMock
from intelligence_engine.soar.automation_engine import SOARAutomationEngine

class TestSOARAutomationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SOARAutomationEngine(
            db_url="postgresql://test:test@localhost/testdb",
            api_key="test_key",
            endpoint="http://test.local/api"
        )

    @patch("intelligence_engine.soar.automation_engine.psycopg2.connect")
    @patch("intelligence_engine.soar.automation_engine.requests.post")
    def test_evaluate_risk_policy_low(self, mock_post, mock_connect):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_post.return_value = mock_response
        
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = self.engine.evaluate_risk_policy(20, "block_ip", {"ip": "1.1.1.1"})
        
        self.assertEqual(result["status"], "executed")
        mock_post.assert_called_once()
        mock_connect.assert_called_once()

    @patch("intelligence_engine.soar.automation_engine.psycopg2.connect")
    def test_evaluate_risk_policy_medium(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = self.engine.evaluate_risk_policy(50, "isolate_host")
        
        self.assertEqual(result["status"], "pending_approval")
        mock_connect.assert_called_once()

    @patch("intelligence_engine.soar.automation_engine.psycopg2.connect")
    def test_evaluate_risk_policy_high(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = self.engine.evaluate_risk_policy(80, "shutdown_server")
        
        self.assertEqual(result["status"], "escalated")
        mock_connect.assert_called_once()

if __name__ == "__main__":
    unittest.main()
