import pytest
from unittest.mock import MagicMock, patch
from intelligence_engine.plugins.compliance.compliance_consumer import ComplianceEvaluator
import time

@pytest.fixture
def evaluator():
    with patch('intelligence_engine.plugins.compliance.compliance_consumer.MemoryLearningSystem') as mock_memory:
        evaluator = ComplianceEvaluator()
        return evaluator

def test_evaluate_event(evaluator):
    evaluator.rules_cache = [
        {"id": 1, "control_id": 101, "expression": "event_type == login"},
        {"id": 2, "control_id": 102, "expression": "user.department == finance"}
    ]
    evaluator.last_sync = time.time() + 100000 # Future time to avoid sync during test
    
    event1 = {"event_type": "login", "user": {"department": "finance"}}
    violations = evaluator.evaluate_event(event1)
    assert len(violations) == 0  # No violations since expected == actual
    
    event2 = {"event_type": "logout", "user": {"department": "hr"}}
    violations = evaluator.evaluate_event(event2)
    assert len(violations) == 2  # Violations for both rules
    assert violations[0]["id"] == 1
    assert violations[1]["id"] == 2

@pytest.mark.asyncio
async def test_handle_violations(evaluator):
    evaluator._get_db = MagicMock()
    mock_cursor = MagicMock()
    evaluator._get_db.return_value.cursor.return_value.__enter__.return_value = mock_cursor

    event = {"tenant_id": 1, "event_id": "test-uuid"}
    violations = [{"id": 1, "control_id": 101, "expression": "event_type == login"}]
    
    with patch('intelligence_engine.plugins.compliance.compliance_consumer.notification_router.route') as mock_route:
        await evaluator.handle_violations(event, violations)
        
        # Verify db insert was called
        mock_cursor.execute.assert_called_once()
        
        # Verify memory system was called
        evaluator.memory_system.record_incident.assert_called_once()
        
        # Verify notification was sent
        mock_route.assert_called_once()
