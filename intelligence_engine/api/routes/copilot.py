import structlog
import json
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

try:
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenAIEmbeddings
    from langchain_core.messages import SystemMessage, HumanMessage
except ImportError:
    ChatGoogleGenerativeAI = None
    GoogleGenAIEmbeddings = None
    SystemMessage = None
    HumanMessage = None

logger = structlog.get_logger(__name__)

# Try to initialize LLM
try:
    from main import llm
except ImportError:
    try:
        from intelligence_engine.main import llm
    except ImportError:
        if ChatGoogleGenerativeAI is not None:
            try:
                from core.optimizations import wrap_llm_with_router
            except ImportError:
                from intelligence_engine.core.optimizations import wrap_llm_with_router
            _base_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)
            llm = wrap_llm_with_router(_base_llm)
        else:
            llm = None

router = APIRouter(tags=["Copilot"])

class QueryRequest(BaseModel):
    query: str

class ExplainRequest(BaseModel):
    investigation_id: str

class ChatRequest(BaseModel):
    query: str

@router.post("/copilot/query")
async def copilot_query(request: QueryRequest):
    if llm is None or SystemMessage is None or HumanMessage is None:
        return {
            "answer": "SOC Copilot query fallback (LLM not available).",
            "evidence": ["Fallback evidence"],
            "confidence": 0.5,
            "sources": ["Local cache"],
            "mitre_mapping": ["T1059"]
        }
    
    sys_msg = SystemMessage(content="You are a SOC Copilot AI. Given the user query, provide a JSON response with fields: answer, evidence (list of strings), confidence (float), sources (list of strings), mitre_mapping (list of strings). Provide ONLY valid JSON.")
    human_msg = HumanMessage(content=request.query)
    
    try:
        response = await llm.ainvoke([sys_msg, human_msg])
        text = response.content.strip()
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Error calling Gemini in copilot_query: {e}")
        return {
            "answer": f"Error generating response: {str(e)}",
            "evidence": [],
            "confidence": 0.0,
            "sources": [],
            "mitre_mapping": []
        }

@router.post("/investigation/explain")
async def investigation_explain(request: ExplainRequest):
    if llm is None or SystemMessage is None or HumanMessage is None:
        return {
            "timeline": ["09:00 - Mock Incident Detected"],
            "root_cause": "SOC Copilot explain fallback (LLM not available).",
            "impact": "Low",
            "recommendations": ["Review credentials"]
        }
    
    sys_msg = SystemMessage(content="You are a SOC Copilot AI. Given an investigation ID, provide a JSON response with fields: timeline (list of strings), root_cause (string), impact (string), recommendations (list of strings). Create a plausible scenario based on the ID. Provide ONLY valid JSON.")
    human_msg = HumanMessage(content=f"Explain investigation {request.investigation_id}")
    
    try:
        response = await llm.ainvoke([sys_msg, human_msg])
        text = response.content.strip()
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"Error calling Gemini in investigation_explain: {e}")
        return {
            "timeline": [],
            "root_cause": f"Error generating explanation: {str(e)}",
            "impact": "Unknown",
            "recommendations": []
        }

@router.post("/chat")
async def chat(request: ChatRequest):
    # Hybrid Qdrant and Neo4j RAG with LLM
    qdrant_context = ""
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        client = db.get_qdrant_client()
        # Retrieve or construct embedding for the query
        if GoogleGenAIEmbeddings is not None:
            embeddings = GoogleGenAIEmbeddings(model="models/embedding-001")
            vector = embeddings.embed_query(request.query)
            results = client.search(
                collection_name="soc_memory",
                query_vector=vector,
                limit=3
            )
            qdrant_context = "\n".join([str(r.payload) for r in results])
        else:
            qdrant_context = "Qdrant client available, but embedding model library not found."
    except Exception as e:
        logger.warning(f"Qdrant search failed, using fallback: {e}")
        qdrant_context = "Fallback Qdrant vector memory context: No matching records found."

    neo4j_context = ""
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        query_str = """
        MATCH (n) 
        WHERE n.id CONTAINS $query OR (exists(n.ip) AND n.ip CONTAINS $query)
        RETURN n, labels(n)[0] AS label LIMIT 5
        """
        results = await db.aexecute_neo4j(query_str, {"query": request.query})
        neo4j_context = "\n".join([f"Node: {r.get('n')}, Label: {r.get('label')}" for r in results])
    except Exception as e:
        logger.warning(f"Neo4j search failed, using fallback: {e}")
        neo4j_context = "Fallback Neo4j graph topology context: Host C-Suite-PC connected to Subnet-1."

    if llm is None or SystemMessage is None or HumanMessage is None:
        return {"response": f"Chat fallback: Qdrant Context: {qdrant_context[:100]} | Neo4j Context: {neo4j_context[:100]}"}

    sys_msg = SystemMessage(content=f"""You are a SOC Copilot AI. Answer the user query using the provided Qdrant vector context and Neo4j graph context.
Qdrant Context:
{qdrant_context}

Neo4j Context:
{neo4j_context}
""")
    human_msg = HumanMessage(content=request.query)

    try:
        response = await llm.ainvoke([sys_msg, human_msg])
        return {"response": response.content.strip()}
    except Exception as e:
        logger.error(f"Error calling Gemini in chat: {e}")
        return {"response": f"Error generating chat response: {str(e)}"}
