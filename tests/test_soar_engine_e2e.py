import pytest
import asyncio
from typing import Dict, Any

from intelligence_engine.soar.core.playbook_parser import PlaybookParser
from intelligence_engine.soar.core.dag_executor import DAGExecutor
from intelligence_engine.soar.hitl.approval_engine import approval_engine
from intelligence_engine.soar.ai.recommender import PlaybookRecommender
from intelligence_engine.soar.core.evidence_vault import EvidenceVault
from intelligence_engine.soar.core.rollback_engine import RollbackEngine
from intelligence_engine.soar.connectors.base import BaseConnector
from intelligence_engine.soar.connectors.registry import ConnectorRegistry

# Register a mock connector for the test
@ConnectorRegistry.register("mock_firewall")
class MockFirewallConnector(BaseConnector):
    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "blocked", "ip": params.get("ip")}

    async def rollback(self, params: Dict[str, Any], context: Dict[str, Any]) -> bool:
        return True


@pytest.mark.asyncio
async def test_full_soar_orchestration_e2e():
    """
    Simulates: Trigger -> Recommender -> DAG Execute -> HITL Pause -> WS Approval -> DAG Resume -> Evidence -> Rollback.
    """
    # 1. AI LangGraph Recommender Node
    recommender = PlaybookRecommender()
    recommendation = await recommender.get_recommendation({"description": "Suspicious login from 10.0.0.5"})
    assert recommendation["recommended_playbook_id"] == "pb_isolate_host_01"
    assert recommendation["confidence"] > 0.9
    
    # 2. DAG Executor (Mock Playbook)
    playbook_def = {
        "nodes": {
            "node_1": {"action": "fetch_logs", "inputs": {"ip": "{{ ip }}"}},
            "node_2": {"action": "manual_approval", "inputs": {"require": "admin"}},
            "node_3": {"action": "block_ip", "inputs": {"ip": "{{ ip }}"}}
        },
        "edges": [
            {"from": "node_1", "to": "node_2"},
            {"from": "node_2", "to": "node_3"}
        ]
    }
    
    # Validate playbook
    parser = PlaybookParser(content="", format="yaml")
    parser.playbook = playbook_def
    parser._validate_structure()
    parser._detect_cycles()
    
    executor = DAGExecutor(playbook_def)
    await executor.init_kafka() # Graceful fallback if no Kafka cluster
    
    context = {"tenant_id": 1, "execution_id": 999, "ip": "10.0.0.5"}
    
    # Mocking _execute_action to handle our specific test nodes
    async def mock_execute_action(action: str, inputs: Dict[str, Any]):
        if action == "fetch_logs":
            return {"logs": "suspicious activity detected"}
        elif action == "manual_approval":
            # 3. HITL Pause & WebSocket Approval
            await approval_engine.request_approval(
                tenant_id=context["tenant_id"],
                execution_id=context["execution_id"],
                node_id="node_2",
                context=context
            )
            # Blocks DAG branch until human responds
            response = await approval_engine.wait_for_approval(context["execution_id"], "node_2")
            if response["action"] != "approve":
                raise Exception("Approval rejected")
            return {"status": "approved", "approver": response["approver_id"]}
        elif action == "block_ip":
            # Use Connector Framework
            connector = ConnectorRegistry.get_connector("mock_firewall", context["tenant_id"])
            return await connector.execute_with_retry(inputs)
            
    executor._execute_action = mock_execute_action

    # 4. Simulate human approving concurrently while DAG is paused
    async def simulate_human_approval():
        await asyncio.sleep(0.1) # Wait for DAG to hit node_2
        await approval_engine.resolve_approval(
            tenant_id=context["tenant_id"],
            execution_id=context["execution_id"],
            node_id="node_2",
            action="approve",
            approver_id=42
        )
        
    dag_task = asyncio.create_task(executor.execute(context))
    human_task = asyncio.create_task(simulate_human_approval())
    
    results, _ = await asyncio.gather(dag_task, human_task)
    
    # Assert DAG succeeded
    assert results["status"] == "SUCCESS"
    assert results["results"]["node_2"]["status"] == "approved"
    assert results["results"]["node_3"]["status"] == "blocked"
    
    # 5. Evidence Vault Hashing
    vault = EvidenceVault()
    evidence_record = await vault.ingest_artifact(
        tenant_id=context["tenant_id"],
        execution_id=context["execution_id"],
        artifact_data=b"raw log data bytes",
        metadata={"source": "node_1"}
    )
    assert "sha256_hash" in evidence_record
    assert evidence_record["sha256_hash"] == "1bcf81d77d621a9537ad6019d4f65ec1d2bd4b6b9f6616a2b4ce87c95250c9b5"
    
    # 6. Rollback Engine
    rollback_engine = RollbackEngine()
    # Mock blast radius verification to return True (safe) since Neo4j is not available in tests
    import unittest.mock
    rollback_engine.verify_blast_radius = unittest.mock.AsyncMock(return_value=True)
    connector = ConnectorRegistry.get_connector("mock_firewall", context["tenant_id"])
    rollback_success = await rollback_engine.execute_rollback(connector, {"asset_id": "fw_01", "ip": "10.0.0.5"}, context)
    assert rollback_success is True

    await executor.close_kafka()
