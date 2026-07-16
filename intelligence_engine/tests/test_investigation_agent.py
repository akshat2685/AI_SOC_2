import pytest
import asyncio
import uuid
import sys
import os

# Ensure the root package is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from intelligence_engine.agents.investigation_agent import build_investigation_graph

@pytest.mark.asyncio
async def test_investigation_workflow_dry_run():
    app = build_investigation_graph()
    
    # Generate mock inputs
    initial_state = {
        "investigation_id": str(uuid.uuid4()),
        "alert_id": "ALERT-9999",
        "context": {
            "description": "Multiple failed logins from unknown IP followed by successful login.",
            "user_id": "admin_01",
            "threat_actor": "APT29"
        },
        "evidence": [],
        "hypotheses": [],
        "attack_story": "",
        "decision": "",
        "confidence": 0.0,
        "recommended_action": "",
        "risk_score": 0,
        "mitre_mapping": []
    }
    
    # Run the graph
    print("Starting LangGraph workflow test...")
    try:
        from unittest.mock import patch, MagicMock
        mock_response = MagicMock()
        mock_response.content = '{"alert_type": "Suspicious Login", "decision": "Contain", "confidence": 0.9, "recommended_action": "Block IP", "mitre_mapping": ["T1078"]}'
        
        with patch("intelligence_engine.agents.investigation_agent.ChatGoogleGenerativeAI.ainvoke", return_value=mock_response), \
             patch("intelligence_engine.agents.investigation_agent.ChatGoogleGenerativeAI.invoke", return_value=mock_response):
            
            final_state = await app.ainvoke(initial_state)
            
            print("\\n=== FINAL STATE ===")
            print(f"Alert Type Evaluated: {final_state['context'].get('alert_type')}")
            print(f"Decision: {final_state.get('decision')}")
            print(f"Confidence: {final_state.get('confidence')}")
            print(f"Action: {final_state.get('recommended_action')}")
            
            # Verify the structure was modified correctly
            assert final_state['context'].get('alert_type') is not None
    except Exception as e:
        pytest.fail(f"Graph execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_investigation_workflow_dry_run())
