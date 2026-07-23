import structlog
from typing import Dict, Any, List
from .core.graph_manager import TwinGraphManager

logger = structlog.get_logger(__name__)

class VulnerabilityOverlay:
    """
    Maps incoming CVE scan results onto Asset nodes, calculating composite CVSS/EPSS scoring.
    """
    def __init__(self, graph_manager: TwinGraphManager):
        self.graph = graph_manager

    async def ingest_vulnerabilities(self, tenant_id: int, asset_id: str, cves: List[Dict[str, Any]]):
        """
        cves = [{'cve_id': 'CVE-2023-123', 'cvss': 9.8, 'epss': 0.85}]
        """
        if not self.graph.driver: return

        composite_score = sum(cve.get("cvss", 0) * cve.get("epss", 1.0) for cve in cves)

        query = """
        MATCH (a:Asset {id: $asset_id, tenant_id: $tenant_id})
        SET a.vulnerability_score = $composite_score
        WITH a
        UNWIND $cves AS cve
        MERGE (v:Vulnerability {id: cve.cve_id, tenant_id: $tenant_id})
        SET v.cvss = cve.cvss, v.epss = cve.epss
        MERGE (a)-[:HAS_VULNERABILITY]->(v)
        """
        async def _do_ingest(tx):
            await tx.run(query, tenant_id=tenant_id, asset_id=asset_id, cves=cves, composite_score=composite_score)

        async with self.graph.driver.session() as session:
            try:
                await session.execute_write(_do_ingest)
            except Exception as e:
                logger.error(f"Error ingesting vulnerabilities: {e}")


class AttackPathAnalyzer:
    """
    Uses Neo4j APOC and Dijkstra algorithms for blast radius and shortest path.
    """
    def __init__(self, graph_manager: TwinGraphManager):
        self.graph = graph_manager

    async def get_shortest_attack_path(self, tenant_id: int, source_id: str, target_id: str) -> Dict[str, Any]:
        """
        Finds the shortest weighted path using Dijkstra's algorithm.
        """
        if not self.graph.driver: return {}
        
        query = """
        MATCH (src:Asset {id: $source_id, tenant_id: $tenant_id})
        MATCH (tgt:Asset {id: $target_id, tenant_id: $tenant_id})
        CALL apoc.algo.dijkstra(src, tgt, 'CONNECTS_TO>', 'weight') YIELD path, weight
        RETURN nodes(path) as path_nodes, weight
        LIMIT 1
        """
        async def _do_query(tx):
            result = await tx.run(query, tenant_id=tenant_id, source_id=source_id, target_id=target_id)
            record = await result.single()
            if record:
                return {"path": [dict(n) for n in record["path_nodes"]], "weight": record["weight"]}
            return {}

        async with self.graph.driver.session() as session:
            try:
                return await session.execute_read(_do_query)
            except Exception as e:
                logger.error(f"Error getting attack path: {e}")
                return {}

    async def get_blast_radius(self, tenant_id: int, asset_id: str) -> List[Dict[str, Any]]:
        """
        Uses apoc.path.subgraphNodes to find all assets reachable within 3 hops.
        """
        if not self.graph.driver: return []
        
        query = """
        MATCH (a:Asset {id: $asset_id, tenant_id: $tenant_id})
        CALL apoc.path.subgraphNodes(a, {
            relationshipFilter: 'CONNECTS_TO>',
            maxLevel: 3
        }) YIELD node
        RETURN node
        """
        async def _do_query(tx):
            result = await tx.run(query, tenant_id=tenant_id, asset_id=asset_id)
            return [dict(r["node"]) async for r in result]

        async with self.graph.driver.session() as session:
            try:
                return await session.execute_read(_do_query)
            except Exception as e:
                logger.error(f"Error getting blast radius: {e}")
                return []


class CrownJewelMapper:
    """
    Tags high-value assets and calculates exposure probabilities.
    """
    def __init__(self, graph_manager: TwinGraphManager):
        self.graph = graph_manager

    async def map_crown_jewels(self, tenant_id: int):
        """
        Finds highly connected internal assets or specific types and flags them.
        """
        if not self.graph.driver: return

        query = """
        MATCH (a:Asset {tenant_id: $tenant_id})
        WHERE a.type = 'Database' OR a.criticality = 'HIGH'
        SET a:CrownJewel
        WITH count(a) as marked_count
        MATCH (old_cj:Asset:CrownJewel {tenant_id: $tenant_id})
        WHERE NOT (old_cj.type = 'Database' OR old_cj.criticality = 'HIGH')
        REMOVE old_cj:CrownJewel
        RETURN marked_count, count(old_cj) as unmarked_count
        """
        async def _do_map(tx):
            res = await tx.run(query, tenant_id=tenant_id)
            record = await res.single()
            return record["marked_count"] if record else 0

        async with self.graph.driver.session() as session:
            try:
                count = await session.execute_write(_do_map)
                logger.info(f"Marked {count} Crown Jewels for tenant {tenant_id}.")
            except Exception as e:
                logger.error(f"Error mapping crown jewels: {e}")
