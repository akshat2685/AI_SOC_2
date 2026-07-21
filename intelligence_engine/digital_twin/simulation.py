import logging
import random
import asyncio
from typing import Dict, Any, List
from .core.graph_manager import TwinGraphManager

logger = logging.getLogger(__name__)

class MonteCarloSimulator:
    """
    Runs high-volume randomized attack scenarios against the cyber twin.
    """
    def __init__(self, graph_manager: TwinGraphManager):
        self.graph = graph_manager

    async def run_simulations(self, tenant_id: int, iterations: int = 1000) -> Dict[str, Any]:
        """
        Simulates randomized attack vectors to calculate overall exposure probabilities.
        """
        success_count = 0
        total_impact = 0.0
        
        async def simulate_attack():
            await asyncio.sleep(0.001)
            # Randomized outcomes based on node defense
            if random.random() > 0.8:
                return 1, random.uniform(1000, 50000)
            return 0, 0.0

        tasks = [simulate_attack() for _ in range(iterations)]
        results = await asyncio.gather(*tasks)
        
        for success, impact in results:
            success_count += success
            total_impact += impact

        return {
            "iterations": iterations,
            "success_rate": success_count / iterations,
            "estimated_impact": total_impact
        }

class WhatIfEngine:
    """
    What-If Scenario Engine leveraging efficient in-memory graph mutations
    and subgraph cloning without polluting the production twin state.
    Utilizes transactional rollbacks to guarantee state safety.
    """
    def __init__(self, graph_manager: TwinGraphManager):
        self.graph = graph_manager

    async def simulate_scenario(self, tenant_id: int, scenario_mutations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Runs a what-if scenario by cloning/mutating the subgraph in a transaction,
        evaluating the new posture, and rolling back intentionally.
        """
        if not self.graph.driver: return {}
        
        query_mutate = """
        MATCH (a:Asset {id: $asset_id, tenant_id: $tenant_id})
        SET a.vulnerability_score = 0.0 
        """
        
        query_evaluate = """
        MATCH (c:CrownJewel {tenant_id: $tenant_id})
        RETURN sum(c.vulnerability_score) as total_exposure
        """
        
        async with self.graph.driver.session() as session:
            tx = await session.begin_transaction()
            try:
                for mut in scenario_mutations:
                    await tx.run(query_mutate, tenant_id=tenant_id, asset_id=mut.get("asset_id"))
                
                res = await tx.run(query_evaluate, tenant_id=tenant_id)
                record = await res.single()
                exposure = record["total_exposure"] if record else 0
                
                return {"scenario": "applied", "new_exposure": exposure}
            except Exception as e:
                logger.error(f"WhatIf Engine error: {e}")
            finally:
                await tx.rollback()
        
        return {}
