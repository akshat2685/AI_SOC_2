"""Canonical SOC Orchestrator — 9-node LangGraph workflow with HITL."""

import os
import json
import asyncio
import time
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from intelligence_engine.ml.detection_engine import AutonomousDetectionEngine
from intelligence_engine.agents.triage_agent import triage_agent
from intelligence_engine.agents.investigation_agent import build_investigation_graph
from intelligence_engine.soar.automation_engine import SOARAutomationEngine

# LLM & service singletons
try:
    from core.optimizations import wrap_llm_with_router
except ImportError:
    from intelligence_engine.core.optimizations import wrap_llm_with_router

_base_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0)
llm = wrap_llm_with_router(_base_llm)
detection_engine = AutonomousDetectionEngine()
soar_engine = SOARAutomationEngine(
    db_url=os.getenv("DATABASE_URL"),
    api_key=os.getenv("SOAR_API_KEY"),
    endpoint=os.getenv("SOAR_API_ENDPOINT"),
)


class SOCState(BaseModel):
    """Pydantic state model for the SOC LangGraph workflow."""
    alert_id: str = ""
    alert_data: Dict[str, Any] = Field(default_factory=dict)
    detection_context: Dict[str, Any] = Field(default_factory=dict)
    triage_priority: str = ""
    triage_detail: Dict[str, Any] = Field(default_factory=dict)
    investigation_findings: List[Dict[str, Any]] = Field(default_factory=list)
    threat_intel_context: Dict[str, Any] = Field(default_factory=dict)
    risk_score: float = 0.0
    severity_score: int = 0
    response_plan: Dict[str, Any] = Field(default_factory=dict)
    soar_execution_results: List[Dict[str, Any]] = Field(default_factory=list)
    final_report: str = ""
    errors: List[str] = Field(default_factory=list)
    hitl_level: int = 0          # 0=auto, 1=high, 2=med+, 3=always
    human_approved: bool = False
    status: str = "pending"


# -- Node 1: Alert ingestion ------------------------------------------------
async def alert_node(state: SOCState) -> Dict[str, Any]:
    print(f"[Alert] Ingesting alert {state.alert_id}")
    return {"alert_data": state.alert_data, "status": "ingested"}


# -- Node 2: Detection (ML) -------------------------------------------------
async def detection_node(state: SOCState) -> Dict[str, Any]:
    print("[Detection] Running ML detection engine.")
    try:
        events = state.alert_data.get("events", [state.alert_data])
        df = detection_engine.extract_features(events)
        threats = detection_engine.hunt_threats(df) if not df.empty else []
        ctx = {"status": "analyzed", "threat_count": len(threats), "threats": threats}
    except Exception as exc:
        ctx = {"status": "error", "error": str(exc)}
    return {"detection_context": ctx}


# -- Node 3: Triage (agent) -------------------------------------------------
async def triage_node(state: SOCState) -> Dict[str, Any]:
    print("[Triage] Delegating to triage agent.")
    try:
        result = await triage_agent(state.alert_data)
        detail = {
            "risk_score": result.get("risk_score", 0),
            "severity": result.get("severity", "Unknown"),
            "decision": result.get("triage_decision", "Investigate"),
        }
        priority = detail["severity"]
    except Exception as exc:
        detail, priority = {"error": str(exc)}, "UNKNOWN"
    return {"triage_priority": priority, "triage_detail": detail}


# -- Node 4: Investigation (sub-graph) --------------------------------------
async def investigation_node(state: SOCState) -> Dict[str, Any]:
    print("[Investigation] Running investigation graph.")
    try:
        inv_graph = build_investigation_graph()
        inv_input = {
            "investigation_id": f"INV-{state.alert_id}",
            "alert_id": state.alert_id,
            "context": {**state.alert_data, **state.detection_context},
            "evidence": [], "hypotheses": [],
            "attack_story": "", "decision": "", "confidence": 0.0,
        }
        r = inv_graph.invoke(inv_input)
        findings = [{
            "decision": r.get("decision", ""),
            "confidence": r.get("confidence", 0.0),
            "attack_story": r.get("attack_story", ""),
        }]
    except Exception as exc:
        findings = [{"error": str(exc)}]
    return {"investigation_findings": findings}


# -- Node 5: Threat Intelligence (LLM) --------------------------------------
async def threat_intel_node(state: SOCState) -> Dict[str, Any]:
    print("[ThreatIntel] Evaluating threat context via LLM.")
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a Threat Intelligence analyst. Given detection context and "
         "investigation findings, produce a JSON object with keys: indicators "
         "(list of IOCs), confidence (high/medium/low), threat_type, summary."),
        ("user", "Detection: {detection}\nInvestigation: {investigation}"),
    ])
    try:
        resp = await (prompt | llm).ainvoke({
            "detection": json.dumps(state.detection_context),
            "investigation": json.dumps(state.investigation_findings),
        })
        intel = json.loads(resp.content)
    except Exception:
        intel = {"indicators": [], "confidence": "low",
                 "threat_type": "unknown", "summary": "LLM call failed"}
    return {"threat_intel_context": intel}


# -- Node 6: Risk scoring (LLM) ---------------------------------------------
async def risk_node(state: SOCState) -> Dict[str, Any]:
    print("[Risk] Calculating risk score via LLM.")
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a Risk Scoring Engine. Return ONLY JSON: "
         '{"risk_score": <0-100>, "severity_score": <0-100>, "rationale": "..."}'),
        ("user",
         "Triage: {triage}\nDetection: {detection}\n"
         "Investigation: {investigation}\nThreat Intel: {threat_intel}"),
    ])
    try:
        resp = await (prompt | llm).ainvoke({
            "triage": json.dumps(state.triage_detail),
            "detection": json.dumps(state.detection_context),
            "investigation": json.dumps(state.investigation_findings),
            "threat_intel": json.dumps(state.threat_intel_context),
        })
        scores = json.loads(resp.content)
        risk = float(scores.get("risk_score", 50))
        severity = int(scores.get("severity_score", 50))
    except Exception:
        risk, severity = 50.0, 50
    return {"risk_score": risk, "severity_score": severity}


# -- Node 7: Response planning (LLM) ----------------------------------------
async def response_node(state: SOCState) -> Dict[str, Any]:
    print("[Response] Generating response plan via LLM.")
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a SOC Response Planner. Produce a JSON response plan with "
         "keys: actions (list), priority, estimated_impact, playbook_id."),
        ("user",
         "Risk Score: {risk_score}\nThreat Intel: {threat_intel}\n"
         "Investigation: {investigation}"),
    ])
    try:
        resp = await (prompt | llm).ainvoke({
            "risk_score": str(state.risk_score),
            "threat_intel": json.dumps(state.threat_intel_context),
            "investigation": json.dumps(state.investigation_findings),
        })
        plan = json.loads(resp.content)
    except Exception:
        plan = {"actions": ["manual_review"], "priority": "medium"}
    return {"response_plan": plan}


# -- HITL conditional edges --------------------------------------------------
def hitl_conditional_edge(state: SOCState) -> Literal["hitl_review", "SOAR"]:
    """Route to human review based on hitl_level and severity_score.
    0=auto, 1=high(>=80), 2=med+(>=50), 3=always."""
    if state.human_approved:
        return "SOAR"
    if state.hitl_level == 3:
        return "hitl_review"
    if state.hitl_level == 2 and state.severity_score >= 50:
        return "hitl_review"
    if state.hitl_level == 1 and state.severity_score >= 80:
        return "hitl_review"
    return "SOAR"


async def hitl_review(state: SOCState) -> Dict[str, Any]:
    """Pause for human-in-the-loop review."""
    print("[HITL] Waiting for human approval.")
    return {"status": "waiting_for_human"}


def after_hitl_edge(state: SOCState) -> Literal["SOAR", "Reporting"]:
    return "SOAR" if state.human_approved else "Reporting"


# -- Node 8: SOAR execution -------------------------------------------------
async def soar_node(state: SOCState) -> Dict[str, Any]:
    print("[SOAR] Executing SOAR playbooks.")
    results = []
    for action in state.response_plan.get("actions", []):
        name = action if isinstance(action, str) else action.get("action", "unknown")
        try:
            outcome = soar_engine.evaluate_risk_policy(
                risk_score=int(state.risk_score), action=name,
                payload=state.response_plan,
            )
            results.append({"action": name, "result": outcome})
        except Exception as exc:
            results.append({"action": name, "error": str(exc)})
    return {"soar_execution_results": results}


# -- Node 9: Reporting (LLM) ------------------------------------------------
async def reporting_node(state: SOCState) -> Dict[str, Any]:
    print("[Reporting] Generating final report via LLM.")
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a SOC Report Generator. Write a concise incident report in "
         "markdown: executive summary, timeline, findings, actions, risk, recs."),
        ("user",
         "Alert: {alert_id}\nRisk: {risk_score}\nInvestigation: {investigation}\n"
         "Response: {response}\nSOAR: {soar}"),
    ])
    try:
        resp = await (prompt | llm).ainvoke({
            "alert_id": state.alert_id,
            "risk_score": str(state.risk_score),
            "investigation": json.dumps(state.investigation_findings),
            "response": json.dumps(state.response_plan),
            "soar": json.dumps(state.soar_execution_results),
        })
        report = resp.content
    except Exception as exc:
        report = f"Report generation failed: {exc}"
    return {"final_report": report, "status": "resolved"}


# -- Graph builder -----------------------------------------------------------
def build_soc_graph() -> StateGraph:
    """Construct the 9-node async LangGraph with HITL conditional edges."""
    wf = StateGraph(SOCState)
    wf.add_node("Alert", alert_node)
    wf.add_node("Detection", detection_node)
    wf.add_node("Triage", triage_node)
    wf.add_node("Investigation", investigation_node)
    wf.add_node("ThreatIntel", threat_intel_node)
    wf.add_node("Risk", risk_node)
    wf.add_node("Response", response_node)
    wf.add_node("hitl_review", hitl_review)
    wf.add_node("SOAR", soar_node)
    wf.add_node("Reporting", reporting_node)

    wf.set_entry_point("Alert")
    wf.add_edge("Alert", "Detection")
    wf.add_edge("Detection", "Triage")
    wf.add_edge("Triage", "Investigation")
    wf.add_edge("Investigation", "ThreatIntel")
    wf.add_edge("ThreatIntel", "Risk")
    wf.add_edge("Risk", "Response")
    wf.add_conditional_edges("Response", hitl_conditional_edge)
    wf.add_conditional_edges("hitl_review", after_hitl_edge)
    wf.add_edge("SOAR", "Reporting")
    wf.add_edge("Reporting", END)
    return wf


soc_app = build_soc_graph().compile()


async def run_orchestrator(
    alert_id: str,
    alert_data: Dict[str, Any] | None = None,
    hitl_level: int = 0,
) -> SOCState:
    """Run the full SOC orchestration pipeline."""
    initial = SOCState(
        alert_id=alert_id,
        alert_data=alert_data or {"id": alert_id},
        hitl_level=hitl_level,
    )
    return await soc_app.ainvoke(initial)


class OrchestratorPool:
    """Manages concurrent automated investigations with a priority queue, worker pool, and circuit breaker."""
    def __init__(self, max_workers: int = 10, error_threshold: int = 5, recovery_timeout: int = 60):
        self.queue = asyncio.PriorityQueue()
        self.max_workers = max_workers
        self.error_threshold = error_threshold
        self.recovery_timeout = recovery_timeout
        self.error_count = 0
        self.circuit_open_time = 0
        self._workers = []

    def _check_circuit_breaker(self) -> bool:
        if self.error_count >= self.error_threshold:
            if time.time() - self.circuit_open_time > self.recovery_timeout:
                self.error_count = self.error_threshold - 1 
                return False
            return True
        return False

    async def submit_alert(self, priority: int, alert_id: str, alert_data: Dict[str, Any] = None, hitl_level: int = 0):
        if self._check_circuit_breaker():
            print(f"[Circuit Breaker] Rejecting alert {alert_id}")
            return
        await self.queue.put((priority, alert_id, alert_data, hitl_level))

    async def _worker(self):
        while True:
            try:
                priority, alert_id, alert_data, hitl_level = await self.queue.get()
                
                if self._check_circuit_breaker():
                    print(f"[Circuit Breaker] Dropping alert {alert_id}")
                    self.queue.task_done()
                    continue

                try:
                    # Use TaskGroup for structured parallel task execution within the worker
                    async with asyncio.TaskGroup() as tg:
                        task = tg.create_task(run_orchestrator(alert_id, alert_data, hitl_level))
                    
                    self.error_count = 0
                    print(f"[OrchestratorPool] Successfully processed {alert_id}")
                except Exception as e:
                    print(f"Error processing alert {alert_id}: {e}")
                    self.error_count += 1
                    if self.error_count == self.error_threshold:
                        self.circuit_open_time = time.time()
                        print("[Circuit Breaker] Tripped!")
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker exception: {e}")

    async def start(self):
        self._workers = [asyncio.create_task(self._worker()) for _ in range(self.max_workers)]

    async def stop(self):
        for w in self._workers:
            w.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)


if __name__ == "__main__":
    async def main():
        pool = OrchestratorPool(max_workers=3)
        await pool.start()
        
        # Submit test alerts
        print("Submitting alerts to OrchestratorPool...")
        await pool.submit_alert(priority=2, alert_id="ALT-1002", alert_data={"id": "ALT-1002", "description": "Suspicious Login"})
        await pool.submit_alert(priority=1, alert_id="ALT-1001", alert_data={"id": "ALT-1001", "description": "Ransomware Activity"})
        
        # Wait for queue to be processed
        await pool.queue.join()
        await pool.stop()
        print("Completed all automated investigations.")
        
    asyncio.run(main())
