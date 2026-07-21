import logging
from typing import List, Dict, Any

try:
    from neo4j import AsyncGraphDatabase
    from neo4j.exceptions import ServiceUnavailable, ClientError
except ImportError:
    AsyncGraphDatabase = None

logger = logging.getLogger(__name__)

class TwinGraphManager:
    """
    Neo4j Graph Manager for Cyber Digital Twin.
    Implements connection pooling, resilient transaction functions,
    and bulk UNWIND upserts for optimal topology synchronization.
    Strictly enforces tenant_id in all queries for RLS isolation.
    """
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        import os
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None

    async def connect(self):
        if AsyncGraphDatabase:
            self.driver = AsyncGraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password),
                max_connection_lifetime=3600,
                max_connection_pool_size=50,
                connection_acquisition_timeout=60.0
            )
            await self._initialize_schema()

    async def close(self):
        if self.driver:
            await self.driver.close()

    async def _initialize_schema(self):
        """Sets up constraints and composite indexes for tenant isolation."""
        queries = [
            "CREATE INDEX asset_tenant_id IF NOT EXISTS FOR (n:Asset) ON (n.tenant_id, n.id)",
            "CREATE INDEX vuln_tenant_id IF NOT EXISTS FOR (v:Vulnerability) ON (v.tenant_id, v.id)"
        ]
        if self.driver:
            async with self.driver.session() as session:
                for q in queries:
                    try:
                        await session.run(q)
                    except Exception as e:
                        logger.warning(f"Failed to create Neo4j index (might require enterprise): {e}")

    async def bulk_upsert_assets(self, tenant_id: int, assets: List[Dict[str, Any]]):
        """
        Uses UNWIND for highly performant batch upserts of assets.
        assets = [{"id": "ip-10-0-0-1", "properties": {"os": "linux", "criticality": "HIGH"}}]
        """
        if not self.driver: return

        query = """
        UNWIND $assets AS asset
        MERGE (n:Asset {id: asset.id, tenant_id: $tenant_id})
        SET n += asset.properties
        """
        async def _do_upsert(tx):
            await tx.run(query, tenant_id=tenant_id, assets=assets)

        async with self.driver.session() as session:
            await session.execute_write(_do_upsert)

    async def bulk_upsert_relationships(self, tenant_id: int, relations: List[Dict[str, Any]]):
        """
        relations = [{"source_id": "ip-1", "target_id": "ip-2", "type": "CONNECTS_TO", "properties": {}}]
        """
        if not self.driver: return
        
        query = """
        UNWIND $relations AS r
        MATCH (src:Asset {id: r.source_id, tenant_id: $tenant_id})
        MATCH (tgt:Asset {id: r.target_id, tenant_id: $tenant_id})
        CALL apoc.create.relationship(src, r.type, r.properties, tgt) YIELD rel
        RETURN count(rel)
        """
        async def _do_upsert(tx):
            await tx.run(query, tenant_id=tenant_id, relations=relations)

        async with self.driver.session() as session:
            try:
                await session.execute_write(_do_upsert)
            except Exception as e:
                logger.error(f"Error upserting relationships (Requires APOC): {e}")
