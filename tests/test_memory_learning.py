import pytest
from unittest.mock import MagicMock, patch
from intelligence_engine.core.memory_learning import MemoryLearningSystem

@pytest.fixture
def memory_system():
    return MemoryLearningSystem(dsn="postgresql://fake:fake@localhost/fake")

@patch("intelligence_engine.core.memory_learning.psycopg.connect")
def test_initialize_schema(mock_connect, memory_system):
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    
    memory_system.initialize_schema()
    
    assert mock_conn.cursor.called
    assert mock_conn.commit.called

@patch("intelligence_engine.core.memory_learning.psycopg.connect")
def test_record_incident(mock_connect, memory_system):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value.__enter__.return_value = mock_conn

    record_id = memory_system.record_incident("INC-123", {"desc": "Malware detected"}, "OPEN")

    assert record_id == 1
    mock_cursor.execute.assert_called_once()
    mock_conn.commit.assert_called_once()

@patch("intelligence_engine.core.memory_learning.psycopg.connect")
def test_request_human_approval(mock_connect, memory_system):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (10,)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value.__enter__.return_value = mock_conn

    approval_id = memory_system.request_human_approval("INC-123", {"action": "Isolate host"})

    assert approval_id == 10
    mock_cursor.execute.assert_called_once()

@patch("intelligence_engine.core.memory_learning.psycopg.connect")
def test_review_action(mock_connect, memory_system):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value.__enter__.return_value = mock_conn

    memory_system.review_action(10, "APPROVED", "Looks good")

    mock_cursor.execute.assert_called_once()
    assert mock_cursor.execute.call_args[0][1] == ("APPROVED", "Looks good", 10)
    mock_conn.commit.assert_called_once()

@patch("intelligence_engine.core.memory_learning.psycopg.connect")
def test_get_pending_approvals(mock_connect, memory_system):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        (1, "INC-123", {"action": "Block IP"}, "PENDING", None)
    ]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value.__enter__.return_value = mock_conn

    results = memory_system.get_pending_approvals()

    assert len(results) == 1
    assert results[0]["incident_id"] == "INC-123"

@patch("intelligence_engine.core.memory_learning.psycopg.connect")
def test_get_incident_memory(mock_connect, memory_system):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("INC-123", {"desc": "Malware detected"}, "RESOLVED")
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_connect.return_value.__enter__.return_value = mock_conn

    result = memory_system.get_incident_memory("INC-123")

    assert result is not None
    assert result["incident_id"] == "INC-123"
    assert result["resolution_status"] == "RESOLVED"
