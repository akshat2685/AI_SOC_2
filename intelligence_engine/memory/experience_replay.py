from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
import uuid

class SOCExperienceReplay:
    def __init__(self, qdrant_url: str):
        self.client = AsyncQdrantClient(url=qdrant_url)
        self.collection_name = "soc_memory"
        
    async def setup(self):
        """ Initializes the hybrid retrieval vector space for SOC Memory. """
        await self.client.recreate_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        
    async def store_experience(self, event: dict, decision: dict, reasoning: str, vector: list[float]):
        """ 
        Store incident memory with O(log n) vector indexing. 
        Addresses Feature 4: Memory Intelligence Upgrade.
        """
        point_id = str(uuid.uuid4())
        await self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id, 
                    vector=vector, 
                    payload={"event": event, "decision": decision, "reasoning": reasoning}
                )
            ]
        )
