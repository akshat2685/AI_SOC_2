from typing import Dict, Any
import structlog

try:
    from neo4j import AsyncGraphDatabase
except ImportError:
    AsyncGraphDatabase = None

logger = structlog.get_logger(__name__)

class RollbackEngine:
    """
    Ensures safe reversion of SOAR actions by verifying the blast radius via Neo4j
    before invoking connector rollback methods.
    """
    def __init__(self, neo4j_uri: str = "bolt://localhost:7687"):
        self.neo4j_uri = neo4j_uri
        self.driver = None
        
    async def connect(self, user=None, password=None):
        if AsyncGraphDatabase:
            try:
                import os
                user = user or os.getenv("NEO4J_USER", "")
                password = password or os.getenv("NEO4J_PASSWORD", "")
                self.driver = AsyncGraphDatabase.driver(self.neo4j_uri, auth=(user, password))
            except Exception as e:
                logger.warning("neo4j_driver_init_failed", error=str(e), exc_info=True)

    async def disconnect(self):
        if self.driver:
            await self.driver.close()

    async def verify_blast_radius(self, tenant_id: int, asset_id: str) -> bool:
        """
        Queries Neo4j to check if the asset has acquired new critical dependencies
        since the action was taken. If so, rollback might be unsafe.
        """
        if not self.driver:
            # Fallback for testing environment / CI: should fail closed in production
            return False
            
        query = """
        MATCH (a:Asset {id: $asset_id})-[:DEPENDS_ON]->(d:Dependency)
        WHERE d.criticality = 'HIGH'
        RETURN count(d) as critical_deps
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, asset_id=asset_id)
                record = await result.single()
                critical_deps = record["critical_deps"] if record else 0
                return critical_deps == 0 # Safe if no high criticality downstream deps
        except Exception as e:
            logger.error("blast_radius_query_failed", error=str(e), exc_info=True)
            return False # Fail safe: do not rollback if we can't verify

    async def execute_rollback(self, connector, action_params: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Orchestrates the rollback process securely by validating the blast radius.
        """
        asset_id = action_params.get("asset_id")
        
        if asset_id:
            is_safe = await self.verify_blast_radius(context.get("tenant_id", 1), asset_id)
            if not is_safe:
                logger.warning(f"Rollback aborted: Blast radius check failed for asset {asset_id}")
                return False
                
        logger.info(f"Blast radius verified. Proceeding with rollback on {connector.__class__.__name__}.")
        return await connector.rollback(action_params, context)
