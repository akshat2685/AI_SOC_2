# Phase 4: LangGraph Implementation Details

## Overview
This document outlines the implementation details for the 9-node asynchronous LangGraph workflow built for the AI Security Operations Center (SOC) Orchestrator. The graph encapsulates the primary lifecycle of a security alert from ingestion to final reporting, integrating conditional human-in-the-loop (HITL) checkpoints.

## File Location
`intelligence_engine/soc_orchestrator.py`

## Typed State Model
We implemented a strict typed state model using Pydantic's `BaseModel` (`SOCState`). 
This ensures type safety and clear schema definition for all data transitioning between nodes.

**State Fields:**
- `alert_id`: Unique identifier for the alert.
- `raw_data`: Raw ingested alert payload.
- `threat_intel`: Enriched threat intelligence data.
- `context`: Internal context (e.g., historical logs, AD roles).
- `analysis`: AI-driven analysis results.
- `severity_score`: Calculated severity score (0-100).
- `hitl_level`: The defined HITL stringency level (0, 1, 2, or 3).
- `human_approved`: Boolean representing if human review granted approval.
- `response_plan`: The formulated remediation plan.
- `execution_result`: Result of executing the remediation plan.
- `report`: The final incident report.
- `status`: Tracking the lifecycle status of the workflow.

## The 9-Node Workflow
Each node is implemented as an asynchronous Python function (`async def`).

1. **`ingestion`**: `ingest_alert` - Parses and ingests the raw alert.
2. **`enrichment`**: `enrich_threat_intel` - Gathers external threat intelligence.
3. **`context_gathering`**: `gather_context` - Collects internal metrics and logs.
4. **`analysis`**: `analyze_alert` - Synthesizes data using ML models/LLMs.
5. **`scoring`**: `score_severity` - Generates a severity score (0-100).
6. **`response_planning`**: `plan_response` - Prepares automated remediation steps.
7. **`hitl_review`**: `hitl_review` - Pause point for manual review (triggered conditionally).
8. **`execution`**: `execute_response` - Performs the remediation actions.
9. **`reporting`**: `generate_report` - Generates the incident resolution report.

## Conditional Edges (Human-in-the-Loop)
The workflow employs LangGraph conditional edges after the `response_planning` phase to determine if Human-in-the-Loop intervention is required.

**HITL Level Logic (`hitl_conditional_edge`):**
- **Level 0**: Fully automated. Always routes directly to `execution`.
- **Level 1**: Human approval required only for high severity events (score >= 80).
- **Level 2**: Human approval required for medium/high severity events (score >= 50).
- **Level 3**: Human approval required for ALL events before execution.

**Post-HITL Routing (`after_hitl_edge`):**
- If `human_approved` is True, it routes to `execution`.
- If `human_approved` is False, it bypasses execution and routes directly to `reporting`.

## Asynchronous Execution
The LangGraph application is compiled and exposed, ready for async invocation via `.ainvoke()`, making it non-blocking and scalable for heavy I/O operations characteristic of an AI SOC.
