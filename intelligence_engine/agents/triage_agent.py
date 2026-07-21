import os
import json
from typing import Dict, TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from intelligence_engine.graph.neo4j_reasoning import AttackGraphReasoningEngine

# Initialize LLM
try:
    from core.optimizations import wrap_llm_with_router
except ImportError:
    from intelligence_engine.core.optimizations import wrap_llm_with_router

_base_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)
llm = wrap_llm_with_router(_base_llm)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")

class TriageState(TypedDict):
    alert_id: str
    raw_alert: Dict
    risk_score: int
    severity: str
    confidence: float
    triage_decision: str
    reasoning: str

async def evaluate_against_graphrag(alert: Dict) -> Dict:
    """Uses GraphRAG to pull blast radius and context for the alert entities."""
    threat_actor = alert.get('threat_actor', alert.get('source_ip', 'Unknown'))
    blast_radius = []
    
    if threat_actor != 'Unknown':
        try:
            password = os.getenv("NEO4J_AUTH", "neo4j/password_in_production").split("/")[1]
            graph_engine = AttackGraphReasoningEngine(NEO4J_URI, "neo4j", password)
            blast_radius = await graph_engine.find_blast_radius(threat_actor)
            await graph_engine.close()
        except Exception as e:
            print(f"[GraphRAG Error in Triage] {e}")
            
    return {"blast_radius_size": len(blast_radius), "graph_context": [dict(r) for r in blast_radius]}

async def triage_agent(alert: Dict) -> TriageState:
    print(f"[Triage Agent] Evaluating Alert {alert.get('id', 'unknown')}...")
    
    # Evaluate context against GraphRAG
    graph_context = await evaluate_against_graphrag(alert)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an Autonomous Triage Engine. Analyze the incoming alert and its GraphRAG context (blast radius). Evaluate Risk (0-100), Severity (Low, Medium, High, Critical), and Confidence (0.0-1.0). Output JSON: {'risk_score': 85, 'severity': 'High', 'confidence': 0.9, 'triage_decision': 'Escalate', 'reasoning': '...'}. Decision must be one of: 'Escalate', 'Investigate', 'Dismiss'."),
        ("user", "Alert: {alert}\nGraph Context: {graph_context}")
    ])
    
    chain = prompt | llm
    state = TriageState(
        alert_id=alert.get('id', 'unknown'),
        raw_alert=alert,
        risk_score=0,
        severity='Low',
        confidence=0.0,
        triage_decision='Investigate',
        reasoning='Failed to evaluate'
    )
    
    try:
        response = await chain.ainvoke({"alert": alert, "graph_context": graph_context})
        clean_json = response.content.strip("```json").strip("```").strip()
        parsed = json.loads(clean_json.replace("'", '"'))
        state['risk_score'] = parsed.get('risk_score', 50)
        state['severity'] = parsed.get('severity', 'Medium')
        state['confidence'] = parsed.get('confidence', 0.5)
        state['triage_decision'] = parsed.get('triage_decision', 'Investigate')
        state['reasoning'] = parsed.get('reasoning', 'No reasoning provided.')
    except Exception as e:
        print(f"[Triage Eval Error] {e}")
        
    return state
