from neo4j import AsyncGraphDatabase

class AttackGraphReasoningEngine:
    def __init__(self, uri, user, password):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        
    async def find_blast_radius(self, threat_actor: str):
        """
        O(V+E) graph traversal to find all assets affected by a threat actor.
        Maps exactly to Feature 3: SOC Knowledge Graph Expansion.
        """
        query = '''
        MATCH (t:ThreatActor {name: $actor})-[:CONDUCTS]->(c:Campaign)-[:TARGETS]->(d:Device)<-[:OWNS]-(u:User)
        RETURN d.hostname AS device, u.name AS user
        '''
        async with self.driver.session() as session:
            result = await session.run(query, actor=threat_actor)
            return [record async for record in result]
            
    async def close(self):
        await self.driver.close()
