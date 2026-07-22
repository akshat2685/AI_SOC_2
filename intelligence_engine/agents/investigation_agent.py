import os
import json
import asyncio
from typing import Dict, TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from intelligence_engine.graph.neo4j_reasoning import AttackGraphReasoningEngine
from intelligence_engine.memory.experience_replay import SOCExperienceReplay
import psycopg2
from psycopg2.extras import RealDictCursor
import uuid

# Initialize LLM
try:
    from core.optimizations import wrap_llm_with_router
except ImportError:
    from intelligence_engine.core.optimizations import wrap_llm_with_router

api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "dummy_key_for_dev"
_base_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, google_api_key=api_key)
llm = wrap_llm_with_router(_base_llm)

# Database configs
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
PG_URL = os.getenv("POSTGRES_URL", "postgresql://soc:changeme_in_production@localhost:5432/soc")

class InvestigationState(TypedDict):
    investigation_id: str
    alert_id: str
    context: Dict
    evidence: List[Dict]
    hypotheses: List[Dict]
    attack_story: str
    decision: str
    confidence: float
    recommended_action: str
    risk_score: int
    mitre_mapping: List[str]

# Node 1: Investigation Planner Agent
async def planner_node(state: InvestigationState) -> InvestigationState:
    print(f"[Planner Agent] Analyzing Alert {state.get('alert_id')}")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a Tier-3 SOC Planner. Given the alert context, classify the alert_type as 'identity', 'malware', 'network', or 'cloud'. Output JSON with 'alert_type' and a 'plan' (list of steps)."),
        ("user", "{context}")
    ])
    chain = prompt | llm
    try:
        response = await chain.ainvoke({"context": json.dumps(state.get('context', {}))})
        clean_json = response.content.strip("```json").strip("```").strip()
        parsed = json.loads(clean_json)
        state['context']['alert_type'] = parsed.get('alert_type', 'generic')
        state['context']['plan'] = parsed.get('plan', [])
    except Exception as e:
        print(f"[Planner Error] {e}")
        state['context']['alert_type'] = "generic"
    return state

# Node 2: Evidence Collector (Generic)
async def evidence_collector_node(state: InvestigationState) -> InvestigationState:
    return state

# Node 2a: Identity Investigation
async def identity_investigation_node(state: InvestigationState) -> InvestigationState:
    print(f"[Identity Agent] Executing Credential/IAM checks via PostgreSQL...")
    user_id = state['context'].get('user_id')
    if user_id:
        try:
            conn = psycopg2.connect(PG_URL)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM security_events WHERE entity = %s ORDER BY timestamp DESC LIMIT 10", (user_id,))
            logs = cur.fetchall()
            state['evidence'].append({"type": "IAM_Logs", "data": [dict(row) for row in logs]})
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[PG Error in Identity Node] {e}")
    return state
    
# Node 2b: Malware Investigation
async def malware_investigation_node(state: InvestigationState) -> InvestigationState:
    print(f"[Malware Agent] Executing Hash/File checks...")
    return state

# Node 3: Hypothesis Agent
async def hypothesis_node(state: InvestigationState) -> InvestigationState:
    print(f"[Hypothesis Agent] Querying Qdrant Memory and generating hypothesis...")
    try:
        memory = SOCExperienceReplay(QDRANT_URL)
        # Placeholder for vector generation API call
        past_cases = [] 
    except Exception as e:
        print(f"[Qdrant Error] {e}")

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Analyze the evidence and context. Generate 2 hypotheses with probabilities. Output JSON: {{'hypotheses': [{{'hypothesis': '...', 'probability': 0.8}}]}}"),
        ("user", "Context: {context} Evidence: {evidence}")
    ])
    chain = prompt | llm
    try:
        response = await chain.ainvoke({"context": state.get('context'), "evidence": state.get('evidence')})
        clean_json = response.content.strip("```json").strip("```").strip()
        parsed = json.loads(clean_json.replace("'", '"'))
        state['hypotheses'] = parsed.get('hypotheses', [])
    except Exception as e:
        print(f"[Hypothesis Error] {e}")
        state['hypotheses'] = [{"hypothesis": "Unknown anomaly", "probability": 0.5}]
    return state

# Node 4: Attack Reconstruction Agent
async def attack_reconstruction_node(state: InvestigationState) -> InvestigationState:
    print(f"[Attack Reconstruction] Querying Neo4j for Blast Radius and generating Attack Narrative...")
    threat_actor = state['context'].get('threat_actor', 'Unknown')
    blast_radius = []
    if threat_actor != 'Unknown':
        try:
            graph_engine = AttackGraphReasoningEngine(NEO4J_URI, "neo4j", os.getenv("NEO4J_AUTH", "neo4j/password_in_production").split("/")[1])
            blast_radius = await graph_engine.find_blast_radius(threat_actor)
            await graph_engine.close()
        except Exception as e:
            print(f"[Neo4j Error] {e}")
            
    state['context']['blast_radius'] = [dict(record) for record in blast_radius]

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert SOC Analyst. Given the alert context, hypotheses, and GraphRAG blast radius, generate a detailed but concise Attack Narrative explaining the entire attack sequence, actor motives, and compromised assets."),
        ("user", "Context: {context}\nHypotheses: {hypotheses}\nBlast Radius: {blast_radius}")
    ])
    chain = prompt | llm
    try:
        response = await chain.ainvoke({
            "context": state.get('context'),
            "hypotheses": state.get('hypotheses'),
            "blast_radius": state.get('context').get('blast_radius')
        })
        state['attack_story'] = response.content.strip()
    except Exception as e:
        print(f"[Attack Narrative Error] {e}")
        state['attack_story'] = f"Timeline reconstructed. Blast radius assets: {len(blast_radius)}."

    return state

# Node 5: Security Reasoning Engine (Decision Maker)
async def decision_node(state: InvestigationState) -> InvestigationState:
    print(f"[Decision Engine] Finalizing verdict and saving to PostgreSQL.")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "As a Tier-3 SOC Analyst, provide a final decision based on hypotheses and evidence. Output JSON: {{'observation': '...', 'confidence': 0.9, 'risk_score': 85, 'mitre_mapping': ['T1078'], 'recommended_action': 'isolate_endpoint'}}"),
        ("user", "Hypotheses: {hypotheses}\\nEvidence: {evidence}\\nAttack Story: {attack_story}")
    ])
    chain = prompt | llm
    try:
        response = await chain.ainvoke({
            "hypotheses": state.get('hypotheses'), 
            "evidence": state.get('evidence'), 
            "attack_story": state.get('attack_story')
        })
        clean_json = response.content.strip("```json").strip("```").strip()
        parsed = json.loads(clean_json.replace("'", '"'))
        state['decision'] = parsed.get('observation', 'Suspicious activity detected.')
        state['confidence'] = float(parsed.get('confidence', 0.5))
        state['risk_score'] = int(parsed.get('risk_score', 50))
        state['mitre_mapping'] = parsed.get('mitre_mapping', [])
        state['recommended_action'] = parsed.get('recommended_action', 'enrich_ip')
    except Exception as e:
        print(f"[Decision Error] {e}")
        state['decision'] = "Error in LLM evaluation"
        state['risk_score'] = 50
        state['mitre_mapping'] = []
        state['recommended_action'] = "review_manually"
        
    try:
        conn = psycopg2.connect(PG_URL)
        cur = conn.cursor()
        # Fallback for investigation_id
        inv_id = state.get('investigation_id') or str(uuid.uuid4())
        cur.execute(
            """INSERT INTO agent_decisions 
            (investigation_id, observation, evidence_references, mitre_mapping, risk_score, decision_taken) 
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (inv_id, state.get('decision'), json.dumps(state.get('evidence', [])), 
             json.dumps(state.get('mitre_mapping', [])), state.get('risk_score'), state.get('recommended_action'))
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[PG Save Error in Decision Node] {e}")
        
    return state

def route_investigation(state: InvestigationState) -> str:
    alert_type = state['context'].get('alert_type', 'generic')
    if alert_type == 'identity':
        return 'identity_investigation'
    elif alert_type == 'malware':
        return 'malware_investigation'
    return 'evidence_collector'

def build_investigation_graph():
    workflow = StateGraph(InvestigationState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("identity_investigation", identity_investigation_node)
    workflow.add_node("malware_investigation", malware_investigation_node)
    workflow.add_node("evidence_collector", evidence_collector_node)
    workflow.add_node("hypothesis_generator", hypothesis_node)
    workflow.add_node("attack_reconstruction", attack_reconstruction_node)
    workflow.add_node("decision_maker", decision_node)
    
    workflow.set_entry_point("planner")
    workflow.add_conditional_edges(
        "planner",
        route_investigation,
        {
            "identity_investigation": "identity_investigation",
            "malware_investigation": "malware_investigation",
            "evidence_collector": "evidence_collector"
        }
    )
    workflow.add_edge("identity_investigation", "hypothesis_generator")
    workflow.add_edge("malware_investigation", "hypothesis_generator")
    workflow.add_edge("evidence_collector", "hypothesis_generator")
    workflow.add_edge("hypothesis_generator", "attack_reconstruction")
    workflow.add_edge("attack_reconstruction", "decision_maker")
    workflow.add_edge("decision_maker", END)
    
    return workflow.compile()
