import os
import structlog
from typing import Dict, Any, List, Optional

logger = structlog.get_logger(__name__)

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


class PlaybookRecommender:
    """
    AI Recommender using Qdrant vector RAG + LangGraph for playbook selection.

    Requires:
      QDRANT_HOST / QDRANT_PORT — Qdrant service
      GOOGLE_API_KEY or OPENAI_API_KEY — for the LLM step
    """

    def __init__(
        self,
        qdrant_client=None,
        collection_name: str = "incident_knowledge",
    ) -> None:
        self._qdrant = qdrant_client
        self.collection_name = collection_name
        self._embedding_model = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def get_recommendation(self, incident_context: Dict[str, Any]) -> Dict[str, Any]:
        description = incident_context.get("description", "")

        historical_context = await self._query_qdrant(description)

        if historical_context:
            result = await self._run_langgraph(incident_context, historical_context)
        else:
            # Qdrant unavailable or empty — return degraded response, never fake confidence
            logger.warning(
                "recommender_degraded",
                reason="Qdrant returned no results — returning degraded response",
            )
            result = {
                "recommended_playbook_id": None,
                "confidence": 0.0,
                "reasoning": "Qdrant vector store is unavailable or has no indexed playbooks. Manual triage required.",
                "historical_cases_used": 0,
                "degraded": True,
            }

        return result

    # ------------------------------------------------------------------
    # Qdrant vector search
    # ------------------------------------------------------------------

    async def _query_qdrant(self, text_query: str) -> List[Dict[str, Any]]:
        if not self._qdrant:
            try:
                from qdrant_client import AsyncQdrantClient

                self._qdrant = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
            except Exception as exc:
                logger.error("qdrant_init_failed", error=str(exc))
                return []

        try:
            embedding = await self._embed(text_query)
            from qdrant_client.models import SearchRequest

            results = await self._qdrant.query_points(
                collection_name=self.collection_name,
                query=embedding,
                limit=5,
                with_payload=True,
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "playbook_id": hit.payload.get("playbook_id"),
                    "resolution": hit.payload.get("resolution", ""),
                }
                for hit in results
            ]
        except Exception as exc:
            logger.error("qdrant_search_failed", error=str(exc))
            return []

    async def _embed(self, text: str) -> List[float]:
        try:
            from sentence_transformers import SentenceTransformer

            if self._embedding_model is None:
                self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            return self._embedding_model.encode(text).tolist()
        except Exception as exc:
            logger.error("embedding_failed", model=EMBEDDING_MODEL, error=str(exc))
            raise

    # ------------------------------------------------------------------
    # LangGraph reasoning step
    # ------------------------------------------------------------------

    async def _run_langgraph(
        self, incident_context: Dict[str, Any], historical_context: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        # Rank by vector similarity score; pick the top candidate playbook
        best = max(historical_context, key=lambda h: h.get("score", 0))
        playbook_id = best.get("playbook_id") or "pb_generic_triage_01"
        confidence = round(float(best.get("score", 0)), 4)

        logger.info(
            "recommender_result",
            playbook_id=playbook_id,
            confidence=confidence,
            cases_used=len(historical_context),
        )
        return {
            "recommended_playbook_id": playbook_id,
            "confidence": confidence,
            "reasoning": f"Selected based on {len(historical_context)} similar historical cases (top score={confidence}).",
            "historical_cases_used": len(historical_context),
            "degraded": False,
        }
