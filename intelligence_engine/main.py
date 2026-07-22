import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from kafka_consumer import consume_events, dlq_consumer_task

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize OpenTelemetry and JSON Logging
    try:
        from core.observability import setup_opentelemetry, setup_json_logging, metrics_worker
    except ImportError:
        from intelligence_engine.core.observability import setup_opentelemetry, setup_json_logging, metrics_worker
        
    setup_opentelemetry()
    setup_json_logging()

    # Start Kafka consumer as a background task when the app starts
    consumer_task = asyncio.create_task(consume_events())
    dlq_task = asyncio.create_task(dlq_consumer_task())
    metrics_task = asyncio.create_task(metrics_worker())
    
    # Start Compliance Processor
    try:
        from plugins.compliance.compliance_consumer import run_compliance_stream
    except ImportError:
        from intelligence_engine.plugins.compliance.compliance_consumer import run_compliance_stream
    compliance_task = asyncio.create_task(run_compliance_stream())
    
    # Start Mesh Client
    import os
    try:
        from core.mesh import NatsMeshClient, LocalMeshClient, AgentProfile
    except ImportError:
        from intelligence_engine.core.mesh import NatsMeshClient, LocalMeshClient, AgentProfile
        
    nats_url = os.getenv("NATS_URL")
    if nats_url:
        app.state.mesh_client = NatsMeshClient(nats_url=nats_url)
    else:
        app.state.mesh_client = LocalMeshClient()
        
    await app.state.mesh_client.connect()
    profile = AgentProfile(node_name="intelligence-engine-core", capabilities=["orchestration", "copilot"], zone="core")
    await app.state.mesh_client.register_agent(profile)

    yield
    # Cancel the task when the app shuts down
    consumer_task.cancel()
    dlq_task.cancel()
    metrics_task.cancel()
    compliance_task.cancel()
    await app.state.mesh_client.disconnect()

app = FastAPI(
    title="EDYSOR-X Intelligence Engine",
    description="Autonomous SOC AI Layer (LangGraph & ML Detectors)",
    version="2.0.0",
    lifespan=lifespan
)

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)
except ImportError:
    pass

try:
    from prometheus_client import make_asgi_app
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
except ImportError:
    pass

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "intelligence-engine"}

@app.post("/api/v1/investigate")
async def trigger_investigation(alert_id: str):
    # This endpoint will eventually trigger the LangGraph Investigation Agent
    return {"status": "accepted", "alert_id": alert_id, "message": "Investigation triggered autonomously."}

# ==========================================
# Task 7: SOC Copilot API Endpoints
# ==========================================
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
import json

class QueryRequest(BaseModel):
    query: str

class ExplainRequest(BaseModel):
    investigation_id: str

# Initialize LLM with Router for Optimization
try:
    from core.optimizations import wrap_llm_with_router
except ImportError:
    from intelligence_engine.core.optimizations import wrap_llm_with_router

api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "dummy_key_for_dev"
_base_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, google_api_key=api_key)
llm = wrap_llm_with_router(_base_llm)

@app.post("/api/v1/copilot/query")
async def copilot_query(request: QueryRequest):
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
        return {
            "answer": f"Error generating response: {str(e)}",
            "evidence": [],
            "confidence": 0.0,
            "sources": [],
            "mitre_mapping": []
        }

@app.post("/api/v1/investigation/explain")
async def investigation_explain(request: ExplainRequest):
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
        return {
            "timeline": [],
            "root_cause": f"Error generating explanation: {str(e)}",
            "impact": "Unknown",
            "recommendations": []
        }
