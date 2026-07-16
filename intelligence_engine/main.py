import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from kafka_consumer import consume_events, dlq_consumer_task

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start Kafka consumer as a background task when the app starts
    consumer_task = asyncio.create_task(consume_events())
    dlq_task = asyncio.create_task(dlq_consumer_task())
    yield
    # Cancel the task when the app shuts down
    consumer_task.cancel()
    dlq_task.cancel()

app = FastAPI(
    title="EDYSOR-X Intelligence Engine",
    description="Autonomous SOC AI Layer (LangGraph & ML Detectors)",
    version="2.0.0",
    lifespan=lifespan
)

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

# Initialize LLM
llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)

@app.post("/api/v1/copilot/query")
async def copilot_query(request: QueryRequest):
    sys_msg = SystemMessage(content="You are a SOC Copilot AI. Given the user query, provide a JSON response with fields: answer, evidence (list of strings), confidence (float), sources (list of strings), mitre_mapping (list of strings). Provide ONLY valid JSON.")
    human_msg = HumanMessage(content=request.query)
    
    try:
        response = llm.invoke([sys_msg, human_msg])
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
        response = llm.invoke([sys_msg, human_msg])
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
