import pytest
import pandas as pd
from intelligence_engine.ml.detection_engine import AutonomousDetectionEngine
from intelligence_engine.agents.soc_orchestrator import (
    SOCState,
    detection_node,
    triage_node,
    investigation_node
)

@pytest.mark.asyncio
async def test_detection_engine_empty_features():
    engine = AutonomousDetectionEngine()
    df = engine.extract_features([])
    assert df.empty

@pytest.mark.asyncio
async def test_detection_node_empty_features_graceful_handling():
    state = SOCState(alert_id="ALT-TEST-01", alert_data={"events": []})
    result = await detection_node(state)
    assert result["detection_context"]["status"] == "no_features"
    assert result["detection_context"]["threats"] == []
