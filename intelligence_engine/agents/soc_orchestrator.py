"""Canonical SOC Orchestrator — 9-node LangGraph workflow with HITL."""

import os
import json
import asyncio
import time
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field, ValidationError
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import structlog

from intelligence_engine.ml.detection_engine import AutonomousDetectionEngine
from intelligence_engine.agents.triage_agent import triage_agent
from intelligence_engine.agents.investigation_agent import build_investigation_graph
from intelligence_engine.soar.automation_engine import SOARAutomationEngine

try:
    from core.optimizations import wrap_llm_with_router
except ImportError:
    from intelligence_engine.core.optimizations import wrap_llm_with_router

logger = structlog.get_logger(__name__)

# ✅ FAIL-FAST: Validate required secrets on startup
def get_required_env(key: str, default: str = None) -> str:
    """Get environment variable or raise ValueError/RuntimeError if missing."""
    value = os.getenv(key, default)
    if not value:
        raise RuntimeError(f"Required environment variable {key} is not set")
    return value

# Get API key (fail fast, no dummy defaults)
api_key = get_required_env("GEMINI_API_KEY")
_base_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, google_api_key=api_key)
llm = wrap_llm_with_router(_base_llm)

detection_engine = AutonomousDetectionEngine()
soar_engine = SOARAutomationEngine(
    db_url=get_required_env("DATABASE_URL"),
    api_key=get_required_env("SOAR_API_KEY"),
    endpoint=get_required_env("SOAR_API_ENDPOINT"),
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
    hitl_level: int = 0
    human_approved: bool = False
    status: str = "pending"


# ✅ PYDANTIC SCHEMAS FOR LLM OUTPUT VALIDATION
class ThreatIntelResponse(BaseModel):
    """Validates threat intelligence LLM response."""
    indicators: List[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    threat_type: str = "unknown"
    summary: str = ""


class RiskScoringResponse(BaseModel):
    """Validates risk scoring LLM response."""
    risk_score: float = Field(ge=0, le=100)
    severity_score: int = Field(ge=0, le=100)
    rationale: str = ""


class ResponsePlanResponse(BaseModel):
    """Validates response plan LLM response."""
    actions: List[str] = Field(default_factory=list)
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    estimated_impact: str = ""
    playbook_id: str = ""


# ✅ NODE 1: Alert ingestion
async def alert_node(state: SOCState) -> Dict[str, Any]:
    """Ingest and validate alert."""
    logger.info("alert_ingested", alert_id=state.alert_id)
    return {"alert_data": state.alert_data, "status": "ingested"}


# ✅ NODE 2: Detection (ML) - With proper error handling
async def detection_node(state: SOCState) -> Dict[str, Any]:
    """Run ML detection engine with structured error handling."""
    logger.info("detection_engine_started", alert_id=state.alert_id)
    
    try:
        events = state.alert_data.get("events", [state.alert_data])
        df = detection_engine.extract_features(events)
        
        if df.empty:
            logger.warning("detection_empty_features", alert_id=state.alert_id)
            return {"detection_context": {"status": "no_features", "threats": []}}
        
        threats = detection_engine.hunt_threats(df)
        ctx = {
            "status": "analyzed",
            "threat_count": len(threats),
            "threats": threats
        }
        logger.info(
            "detection_completed",
            alert_id=state.alert_id,
            threat_count=len(threats)
        )
        return {"detection_context": ctx}
        
    except Exception as exc:
        logger.error(
            "detection_failed",
            alert_id=state.alert_id,
            error=str(exc),
            exc_info=True
        )
        state.errors.append(f"Detection failed: {str(exc)}")
        return {
            "detection_context": {
                "status": "error",
                "error": str(exc),
                "threats": []
            }
        }


# ✅ NODE 3: Triage (agent) - With structured error handling
async def triage_node(state: SOCState) -> Dict[str, Any]:
    """Delegate to triage agent with error handling."""
    logger.info("triage_started", alert_id=state.alert_id)
    
    try:
        result = await triage_agent(state.alert_data)
        detail = {
            "risk_score": result.get("risk_score", 0),
            "severity": result.get("severity", "Unknown"),
            "decision": result.get("triage_decision", "Investigate"),
            "reasoning": result.get("reasoning", "")
        }
        priority = detail["severity"]
        logger.info(
            "triage_completed",
            alert_id=state.alert_id,
            priority=priority,
            risk_score=detail["risk_score"]
        )
        
    except asyncio.TimeoutError:
        logger.error(
            "triage_timeout",
            alert_id=state.alert_id,
            timeout_seconds=30
        )
        detail = {
            "error": "triage_timeout",
            "risk_score": 50,
            "severity": "MEDIUM",
            "decision": "ManualReview"
        }
        priority = "MEDIUM"
        state.errors.append("Triage agent timed out")
        
    except Exception as exc:
        logger.error(
            "triage_failed",
            alert_id=state.alert_id,
            error=str(exc),
            exc_info=True
        )
        detail = {
            "error": str(exc),
            "risk_score": 50,
            "severity": "MEDIUM",
            "decision": "ManualReview"
        }
        priority = "MEDIUM"
        state.errors.append(f"Triage failed: {str(exc)}")
    
    return {"triage_priority": priority, "triage_detail": detail}


# ✅ NODE 4: Investigation (sub-graph)
async def investigation_node(state: SOCState) -> Dict[str, Any]:
    """Run investigation graph with error handling."""
    logger.info("investigation_started", alert_id=state.alert_id)
    
    try:
        inv_graph = build_investigation_graph()
        inv_input = {
            "investigation_id": f"INV-{state.alert_id}",
            "alert_id": state.alert_id,
            "context": {**state.alert_data, **state.detection_context},
            "evidence": [],
            "hypotheses": [],
            "attack_story": "",
            "decision": "",
            "confidence": 0.0,
        }
        r = inv_graph.invoke(inv_input)
        findings = [{
            "decision": r.get("decision", ""),
            "confidence": r.get("confidence", 0.0),
            "attack_story": r.get("attack_story", ""),
        }]
        logger.info(
            "investigation_completed",
            alert_id=state.alert_id,
            confidence=findings[0]["confidence"]
        )
        
    except Exception as exc:
        logger.error(
            "investigation_failed",
            alert_id=state.alert_id,
            error=str(exc),
            exc_info=True
        )
        findings = [{
            "error": str(exc),
            "decision": "unknown",
            "confidence": 0.0,
        }]
        state.errors.append(f"Investigation failed: {str(exc)}")
    
    return {"investigation_findings": findings}


# ✅ NODE 5: Threat Intelligence - With Pydantic validation
async def threat_intel_node(state: SOCState) -> Dict[str, Any]:
    """Evaluate threat context via LLM with structured parsing."""
    logger.info("threat_intel_started", alert_id=state.alert_id)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a Threat Intelligence analyst. Given detection context and "
         "investigation findings, produce a JSON object with keys: indicators "
         "(list of IOCs), confidence (high/medium/low), threat_type, summary."),
        ("user", "Detection: {detection}\nInvestigation: {investigation}"),
    ])
    
    parser = JsonOutputParser(pydantic_object=ThreatIntelResponse)
    
    try:
        intel = await (prompt | llm | parser).ainvoke({
            "detection": json.dumps(state.detection_context),
            "investigation": json.dumps(state.investigation_findings),
        })
        logger.info(
            "threat_intel_completed",
            alert_id=state.alert_id,
            threat_type=intel.threat_type,
            confidence=intel.confidence
        )
        return {"threat_intel_context": intel.model_dump()}
        
    except ValidationError as e:
        logger.error(
            "threat_intel_validation_failed",
            alert_id=state.alert_id,
            validation_error=str(e)
        )
        # Fallback response
        return {
            "threat_intel_context": {
                "indicators": [],
                "confidence": "low",
                "threat_type": "unknown",
                "summary": "Failed to evaluate threat intelligence"
            }
        }
    except Exception as exc:
        logger.error(
            "threat_intel_failed",
            alert_id=state.alert_id,
            error=str(exc),
            exc_info=True
        )
        state.errors.append(f"Threat intel failed: {str(exc)}")
        return {
            "threat_intel_context": {
                "indicators": [],
                "confidence": "low",
                "threat_type": "unknown",
                "summary": f"Error: {str(exc)}"
            }
        }


# ✅ NODE 6: Risk scoring - With Pydantic validation
async def risk_node(state: SOCState) -> Dict[str, Any]:
    """Calculate risk score via LLM with structured parsing."""
    logger.info("risk_scoring_started", alert_id=state.alert_id)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a Risk Scoring Engine. Return ONLY JSON: "
         '{"risk_score": <0-100>, "severity_score": <0-100>, "rationale": "..."}'),
        ("user",
         "Triage: {triage}\nDetection: {detection}\n"
         "Investigation: {investigation}\nThreat Intel: {threat_intel}"),
    ])
    
    parser = JsonOutputParser(pydantic_object=RiskScoringResponse)
    
    try:
        scores = await (prompt | llm | parser).ainvoke({
            "triage": json.dumps(state.triage_detail),
            "detection": json.dumps(state.detection_context),
            "investigation": json.dumps(state.investigation_findings),
            "threat_intel": json.dumps(state.threat_intel_context),
        })
        logger.info(
            "risk_scoring_completed",
            alert_id=state.alert_id,
            risk_score=scores.risk_score,
            severity_score=scores.severity_score
        )
        return {
            "risk_score": float(scores.risk_score),
            "severity_score": int(scores.severity_score)
        }
        
    except ValidationError as e:
        logger.error(
            "risk_scoring_validation_failed",
            alert_id=state.alert_id,
            validation_error=str(e)
        )
        # Fallback: medium risk
        return {"risk_score": 50.0, "severity_score": 50}
        
    except Exception as exc:
        logger.error(
            "risk_scoring_failed",
            alert_id=state.alert_id,
            error=str(exc),
            exc_info=True
        )
        state.errors.append(f"Risk scoring failed: {str(exc)}")
        return {"risk_score": 50.0, "severity_score": 50}


# ✅ NODE 7: Response planning - With Pydantic validation
async def response_node(state: SOCState) -> Dict[str, Any]:
    """Generate response plan via LLM with structured parsing."""
    logger.info("response_planning_started", alert_id=state.alert_id)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a SOC Response Planner. Produce a JSON response plan with "
         "keys: actions (list), priority, estimated_impact, playbook_id."),
        ("user",
         "Risk Score: {risk_score}\nThreat Intel: {threat_intel}\n"
         "Investigation: {investigation}"),
    ])
    
    parser = JsonOutputParser(pydantic_object=ResponsePlanResponse)
    
    try:
        plan = await (prompt | llm | parser).ainvoke({
            "risk_score": str(state.risk_score),
            "threat_intel": json.dumps(state.threat_intel_context),
            "investigation": json.dumps(state.investigation_findings),
        })
        logger.info(
            "response_planning_completed",
            alert_id=state.alert_id,
            action_count=len(plan.actions),
            priority=plan.priority
        )
        return {"response_plan": plan.model_dump()}
        
    except ValidationError as e:
        logger.error(
            "response_planning_validation_failed",
            alert_id=state.alert_id,
            validation_error=str(e)
        )
        return {
            "response_plan": {
                "actions": ["manual_review"],
                "priority": "medium",
                "estimated_impact": "Unknown"
            }
        }
    except Exception as exc:
        logger.error(
            "response_planning_failed",
            alert_id=state.alert_id,
            error=str(exc),
            exc_info=True
        )
        state.errors.append(f"Response planning failed: {str(exc)}")
        return {
            "response_plan": {
                "actions": ["manual_review"],
                "priority": "medium",
                "estimated_impact": "Unknown"
            }
        }


# ✅ HITL conditional edges (unchanged)
def hitl_conditional_edge(state: SOCState) -> Literal["hitl_review", "SOAR"]:
    """Route to human review based on hitl_level and severity_score."""
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
    logger.info("hitl_review_started", alert_id=state.alert_id)
    return {"status": "waiting_for_human"}


def after_hitl_edge(state: SOCState) -> Literal["SOAR", "Reporting"]:
    return "SOAR" if state.human_approved else "Reporting"


# ✅ NODE 8: SOAR execution
async def soar_node(state: SOCState) -> Dict[str, Any]:
    """Execute SOAR playbooks with error handling."""
    logger.info("soar_execution_started", alert_id=state.alert_id)
    
    results = []
    for action in state.response_plan.get("actions", []):
        name = action if isinstance(action, str) else action.get("action", "unknown")
        try:
            outcome = await soar_engine.evaluate_risk_policy(
                risk_score=int(state.risk_score),
                action=name,
                payload=state.response_plan,
            )
            results.append({"action": name, "result": outcome})
            logger.info(
                "soar_action_executed",
                alert_id=state.alert_id,
                action=name,
                result_status=outcome.get("status", "unknown")
            )
        except Exception as exc:
            logger.error(
                "soar_action_failed",
                alert_id=state.alert_id,
                action=name,
                error=str(exc),
                exc_info=True
            )
            results.append({"action": name, "error": str(exc)})
            state.errors.append(f"SOAR action {name} failed: {str(exc)}")
    
    return {"soar_execution_results": results}


# ✅ NODE 9: Reporting
async def reporting_node(state: SOCState) -> Dict[str, Any]:
    """Generate final report via LLM."""
    logger.info("reporting_started", alert_id=state.alert_id)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You are a SOC Report Generator. Write a concise incident report in "
         "markdown: executive summary, timeline, findings, actions, risk, recs."),
        ("user",
         "Alert: {alert_id}\nRisk: {risk_score}\nInvestigation: {investigation}\n"
         "Response: {response}\nSOAR: {soar}\nErrors: {errors}"),
    ])
    
    try:
        resp = await (prompt | llm).ainvoke({
            "alert_id": state.alert_id,
            "risk_score": str(state.risk_score),
            "investigation": json.dumps(state.investigation_findings),
            "response": json.dumps(state.response_plan),
            "soar": json.dumps(state.soar_execution_results),
            "errors": json.dumps(state.errors),
        })
        report = resp.content
        logger.info(
            "reporting_completed",
            alert_id=state.alert_id,
            report_length=len(report)
        )
        return {"final_report": report, "status": "resolved"}
        
    except Exception as exc:
        logger.error(
            "reporting_failed",
            alert_id=state.alert_id,
            error=str(exc),
            exc_info=True
        )
        state.errors.append(f"Report generation failed: {str(exc)}")
        return {
            "final_report": f"# Incident Report: {state.alert_id}\n\nInvestigation failed with errors:\n" +
                           "\n".join(f"- {e}" for e in state.errors),
            "status": "failed"
        }


# ✅ Graph builder (unchanged)
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
    logger.info("orchestrator_started", alert_id=alert_id, hitl_level=hitl_level)
    
    initial = SOCState(
        alert_id=alert_id,
        alert_data=alert_data or {"id": alert_id},
        hitl_level=hitl_level,
    )
    
    try:
        result = await soc_app.ainvoke(initial)
        logger.info(
            "orchestrator_completed",
            alert_id=alert_id,
            status=result.get("status", "completed"),
            risk_score=result.get("risk_score", 0.0),
            error_count=len(result.get("errors", []))
        )
        return result
    except Exception as e:
        logger.error(
            "orchestrator_failed",
            alert_id=alert_id,
            error=str(e),
            exc_info=True
        )
        raise


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

    async def submit_alert(
        self,
        priority: int,
        alert_id: str,
        alert_data: Dict[str, Any] = None,
        hitl_level: int = 0
    ):
        if self._check_circuit_breaker():
            logger.warning(
                "circuit_breaker_active",
                alert_id=alert_id,
                rejecting=True
            )
            return
        await self.queue.put((priority, alert_id, alert_data, hitl_level))

    async def _worker(self):
        while True:
            try:
                priority, alert_id, alert_data, hitl_level = await self.queue.get()
                
                if self._check_circuit_breaker():
                    logger.warning(
                        "circuit_breaker_dropped_alert",
                        alert_id=alert_id
                    )
                    self.queue.task_done()
                    continue

                try:
                    async with asyncio.TaskGroup() as tg:
                        task = tg.create_task(
                            run_orchestrator(alert_id, alert_data, hitl_level)
                        )
                    
                    self.error_count = 0
                    logger.info("orchestrator_pool_success", alert_id=alert_id)
                    
                except Exception as e:
                    logger.error(
                        "orchestrator_pool_error",
                        alert_id=alert_id,
                        error=str(e),
                        exc_info=True
                    )
                    self.error_count += 1
                    if self.error_count == self.error_threshold:
                        self.circuit_open_time = time.time()
                        logger.critical("circuit_breaker_tripped")
                finally:
                    self.queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("orchestrator_pool_worker_exception", error=str(e), exc_info=True)

    async def start(self):
        """Start worker threads."""
        self._workers = [
            asyncio.create_task(self._worker()) for _ in range(self.max_workers)
        ]
        logger.info("orchestrator_pool_started", worker_count=self.max_workers)

    async def stop(self):
        """Stop worker threads gracefully."""
        for w in self._workers:
            w.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        logger.info("orchestrator_pool_stopped")


if __name__ == "__main__":
    async def main():
        pool = OrchestratorPool(max_workers=3)
        await pool.start()
        
        logger.info("submitting_test_alerts")
        await pool.submit_alert(
            priority=2,
            alert_id="ALT-1002",
            alert_data={"id": "ALT-1002", "description": "Suspicious Login"}
        )
        await pool.submit_alert(
            priority=1,
            alert_id="ALT-1001",
            alert_data={"id": "ALT-1001", "description": "Ransomware Activity"}
        )
        
        await pool.queue.join()
        await pool.stop()
        logger.info("all_investigations_completed")
        
    asyncio.run(main())
