import pytest
import asyncio
from intelligence_engine.core.clickhouse_writer import ClickHouseWriter
from intelligence_engine.soar.automation_engine import SOARAutomationEngine

@pytest.mark.asyncio
async def test_clickhouse_writer_concurrent_batch_writes():
    writer = ClickHouseWriter(host="localhost", port=8123)
    # Mock client to avoid needing running ClickHouse instance during unit tests
    class MockClient:
        def insert(self, table, data, column_names):
            pass
    writer.client = MockClient()

    events1 = [{"id": i, "event": "login"} for i in range(50)]
    events2 = [{"id": i, "event": "logout"} for i in range(50)]

    await asyncio.gather(
        writer.write_batch(events1),
        writer.write_batch(events2)
    )

    assert len(writer.buffer) <= 100

@pytest.mark.asyncio
async def test_soar_automation_engine_policy_evaluation():
    engine = SOARAutomationEngine()
    res_low = await engine.evaluate_risk_policy(20, "isolate_ip")
    assert res_low["status"] in ["executed", "failed"]

    res_med = await engine.evaluate_risk_policy(50, "revoke_token")
    assert res_med["status"] == "pending_approval"

    res_high = await engine.evaluate_risk_policy(90, "shutdown_server")
    assert res_high["status"] == "escalated"
