import asyncio
import os
import json
from typing import Dict, Any, Literal, TypedDict
from pydantic import BaseModel, Field, ValidationError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import structlog

from intelligence_engine.graph.neo4j_reasoning import AttackGraphReasoningEngine

try:
    from core.optimizations import wrap_llm_with_router
except ImportError:
    from intelligence_engine.core.optimizations import wrap_llm_with_router

logger = structlog.get_logger(__name__)

def get_required_env(key: str, default: str = None) -> str:
    value = os.getenv(key, default)
    if not value:
        raise RuntimeError(f"Required environment variable {key} is not set")
    return value

def _get_api_key() -> str:
    """Resolve the Gemini API key at call time, not import time.

    The backend must boot without a key (agents stay dark until one is
    configured); failing here would crash the whole API on import.
    """
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set: the triage agent "
            "needs a Gemini API key. Set it to enable AI triage."
        )
    return key


_llm = None

def get_llm():
    """Lazily build (and cache) the triage LLM client."""
    global _llm
    if _llm is None:
        _llm = wrap_llm_with_router(
            ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, google_api_key=_get_api_key())
        )
    return _llm


# Backwards-compatible module aliases (resolved lazily; do not use at import time).
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
llm = None  # use get_llm() instead; kept as a name so old imports don't break

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")


class TriageState(TypedDict):
    alert_id: str
    raw_alert: Dict[str, Any]
    risk_score: int
    severity: str
    confidence: float
    triage_decision: str
    reasoning: str


class TriageLLMResponse(BaseModel):
    """Pydantic model for validating triage LLM outputs."""
    risk_score: int = Field(ge=0, le=100, default=50)
    severity: Literal["Low", "Medium", "High", "Critical"] = "Medium"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    triage_decision: Literal["Escalate", "Investigate", "Dismiss"] = "Investigate"
    reasoning: str = "No reasoning provided."


async def evaluate_against_graphrag(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Uses GraphRAG to pull blast radius and context for the alert entities."""
    threat_actor = alert.get('threat_actor', alert.get('source_ip', 'Unknown'))
    blast_radius = []
    
    if threat_actor != 'Unknown':
        try:
            # Env-only credentials: NEO4J_PASSWORD (preferred) or legacy NEO4J_AUTH=user/pass.
            # No hardcoded default password -- without one we skip GraphRAG.
            neo4j_auth = os.getenv("NEO4J_AUTH", "")
            password = os.getenv("NEO4J_PASSWORD") or (neo4j_auth.split("/")[1] if "/" in neo4j_auth else "")
            if not password:
                raise RuntimeError("NEO4J_PASSWORD (or NEO4J_AUTH) is not set: skipping GraphRAG context")
            graph_engine = AttackGraphReasoningEngine(NEO4J_URI, os.getenv("NEO4J_USER", "neo4j"), password)
            # Fail fast when Neo4j is absent (MVP: graph is optional). Without a
            # timeout the driver's connection retries block the worker for ~30s+.
            blast_radius = await asyncio.wait_for(
                graph_engine.find_blast_radius(threat_actor), timeout=10
            )
            await graph_engine.close()
            logger.info("graphrag_triage_completed", threat_actor=threat_actor, count=len(blast_radius))
        except Exception as e:
            logger.error("graphrag_triage_failed", error=str(e), exc_info=True)
            
    return {"blast_radius_size": len(blast_radius), "graph_context": [dict(r) for r in blast_radius]}


async def triage_agent(alert: Dict[str, Any]) -> TriageState:
    alert_id = str(alert.get('id', 'unknown'))
    logger.info("triage_agent_evaluation_started", alert_id=alert_id)
    
    # Evaluate context against GraphRAG
    graph_context = await evaluate_against_graphrag(alert)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an Autonomous Triage Engine. Analyze the incoming alert and its GraphRAG context (blast radius). Evaluate Risk (0-100), Severity (Low, Medium, High, Critical), and Confidence (0.0-1.0). Output JSON: {{'risk_score': 85, 'severity': 'High', 'confidence': 0.9, 'triage_decision': 'Escalate', 'reasoning': '...'}}. Decision must be one of: 'Escalate', 'Investigate', 'Dismiss'."),
        ("user", "Alert: {alert}\nGraph Context: {graph_context}")
    ])
    
    parser = JsonOutputParser(pydantic_object=TriageLLMResponse)
    chain = prompt | get_llm() | parser
    
    state: TriageState = {
        'alert_id': alert_id,
        'raw_alert': alert,
        'risk_score': 0,
        'severity': 'Low',
        'confidence': 0.0,
        'triage_decision': 'Investigate',
        'reasoning': 'Failed to evaluate'
    }
    
    try:
        parsed: TriageLLMResponse = await chain.ainvoke({"alert": alert, "graph_context": graph_context})
        state['risk_score'] = parsed.risk_score
        state['severity'] = parsed.severity
        state['confidence'] = parsed.confidence
        state['triage_decision'] = parsed.triage_decision
        state['reasoning'] = parsed.reasoning
        logger.info(
            "triage_agent_evaluation_completed",
            alert_id=alert_id,
            decision=parsed.triage_decision,
            risk_score=parsed.risk_score,
            severity=parsed.severity
        )
    except ValidationError as ve:
        logger.error("triage_agent_validation_error", alert_id=alert_id, error=str(ve))
        state['risk_score'] = 50
        state['severity'] = 'Medium'
        state['confidence'] = 0.5
        state['triage_decision'] = 'Investigate'
        state['reasoning'] = 'Pydantic validation failed, defaulted to medium risk'
    except Exception as e:
        logger.error("triage_agent_evaluation_failed", alert_id=alert_id, error=str(e), exc_info=True)
        state['reasoning'] = f"Error during triage evaluation: {str(e)}"
        
    return state
