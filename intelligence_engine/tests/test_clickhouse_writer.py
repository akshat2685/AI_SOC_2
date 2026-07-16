import pytest
from unittest.mock import MagicMock, patch
from intelligence_engine.core.clickhouse_writer import ClickHouseWriter

def test_clickhouse_writer_connect():
    with patch('intelligence_engine.core.clickhouse_writer.clickhouse_connect.get_client') as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        writer = ClickHouseWriter(host='localhost', port=8123)
        writer.connect()
        
        mock_get_client.assert_called_once_with(host='localhost', port=8123, username='default', password='')
        assert writer.client == mock_client

@pytest.mark.asyncio
async def test_clickhouse_writer_batch_flush():
    writer = ClickHouseWriter(host='localhost', port=8123)
    writer.client = MagicMock()
    writer.max_batch_size = 2
    
    event1 = {"event_id": "1", "type": "A"}
    event2 = {"event_id": "2", "type": "B"}
    
    # Should not flush yet
    await writer.write_batch([event1])
    assert len(writer.buffer) == 1
    writer.client.insert.assert_not_called()
    
    # Should flush now
    await writer.write_batch([event2])
    assert len(writer.buffer) == 0
    writer.client.insert.assert_called_once()
    
    args, kwargs = writer.client.insert.call_args
    assert args[0] == 'soc_events'
    assert len(args[1]) == 2 # data
    assert kwargs['column_names'] == list(event1.keys())
    assert args[1][0] == [event1[col] for col in kwargs['column_names']]

def test_clickhouse_writer_query():
    writer = ClickHouseWriter(host='localhost', port=8123)
    writer.client = MagicMock()
    
    mock_result = MagicMock()
    mock_result.result_rows = [("test", 1)]
    writer.client.query.return_value = mock_result
    
    res = writer.query("SELECT * FROM test")
    writer.client.query.assert_called_once_with("SELECT * FROM test")
    assert res == [("test", 1)]

@pytest.mark.asyncio
async def test_clickhouse_writer_flush_failure():
    writer = ClickHouseWriter(host='localhost', port=8123)
    writer.client = MagicMock()
    writer.client.insert.side_effect = Exception("DB down")
    
    event1 = {"event_id": "1", "type": "A"}
    writer.buffer = [event1]
    
    with patch('intelligence_engine.core.clickhouse_writer.route_to_dlq') as mock_dlq:
        await writer.flush()
        writer.client.insert.assert_called_once()
        mock_dlq.assert_called_once_with(event1, "ClickHouse insert failed: DB down")
        # Ensure buffer was cleared despite error
        assert len(writer.buffer) == 0

