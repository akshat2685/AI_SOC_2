import pytest
import asyncio

from intelligence_engine.digital_twin.core.graph_manager import TwinGraphManager
from intelligence_engine.digital_twin.analyzers import VulnerabilityOverlay, AttackPathAnalyzer, CrownJewelMapper
from intelligence_engine.digital_twin.simulation import MonteCarloSimulator, WhatIfEngine
from intelligence_engine.digital_twin.posture import PostureCalculator
from intelligence_engine.digital_twin.ai_predictor import LangGraphRiskPredictor

@pytest.mark.asyncio
async def test_full_digital_twin_pipeline():
    """
    E2E integration test for the Cyber Digital Twin Engine.
    Simulates: Graph Manager Init -> Vuln Ingest -> Attack Path -> Monte Carlo -> Posture -> Risk Prediction.
    """
    import os
    os.environ["NEO4J_URI"] = "bolt://invalid_host:7687"
    os.environ["NEO4J_PASSWORD"] = "password_in_production"
    tenant_id = 1
    
    # 1. Graph Manager (Graceful fallback if Neo4j is offline)
    gm = TwinGraphManager()
    import unittest.mock
    gm.connect = unittest.mock.AsyncMock()
    await gm.connect()
    
    # 2. Vulnerability Ingest
    vuln_overlay = VulnerabilityOverlay(gm)
    await vuln_overlay.ingest_vulnerabilities(tenant_id, "asset-1", [{"cve_id": "CVE-2024-1234", "cvss": 9.0, "epss": 0.8}])
    
    # 3. Attack Path & Crown Jewel
    path_analyzer = AttackPathAnalyzer(gm)
    path = await path_analyzer.get_shortest_attack_path(tenant_id, "asset-1", "asset-10")
    
    mapper = CrownJewelMapper(gm)
    await mapper.map_crown_jewels(tenant_id)
    
    # 4. Simulation
    mc = MonteCarloSimulator(gm)
    mc_results = await mc.run_simulations(tenant_id, iterations=10)
    assert mc_results["iterations"] == 10
    assert "success_rate" in mc_results
    
    what_if = WhatIfEngine(gm)
    wi_res = await what_if.simulate_scenario(tenant_id, [{"asset_id": "asset-1", "mutation": "patch"}])
    
    # 5. Posture Score
    calculator = PostureCalculator()
    posture = calculator.calculate_posture(tenant_id, vulnerabilities=5, exposure_rate=0.2, incidents=1)
    assert posture["tenant_id"] == tenant_id
    assert posture["posture_score"] > 0
    assert posture["financial_impact_at_risk"] > 0
    
    # 6. AI Predictor
    predictor = LangGraphRiskPredictor()
    import unittest.mock
    predictor.predict_risk = unittest.mock.AsyncMock(return_value={
        "probability": 0.85,
        "recommended_playbook": "pb_isolate_and_contain",
        "reasoning": "Mocked for E2E testing"
    })
    prediction = await predictor.predict_risk(tenant_id, {"id": "asset-1"}, {})
    assert prediction["probability"] == 0.85
    assert prediction["recommended_playbook"] == "pb_isolate_and_contain"
    
    await gm.close()
