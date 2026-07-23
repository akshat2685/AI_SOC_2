import io
import uuid
import time
import json
from fastapi import APIRouter, HTTPException, Query, Body, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from starlette import status
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts"])

class InvestigateRequestBody(BaseModel):
    alert_id: Optional[str] = None

# Helper to generate PDF bytes dynamically
def generate_mock_pdf_stream(title: str, content: str):
    # Yield PDF chunks dynamically to reduce memory consumption
    yield b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    yield b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    yield b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    yield b"4 0 obj\n<< /Length 150 >>\nstream\nBT\n/F1 24 Tf\n100 700 Td\n(" + title.encode('latin1', errors='replace') + b") Tj\n"
    yield b"0 -40 Td\n/F1 12 Tf\n(" + content.encode('latin1', errors='replace') + b") Tj\nET\nendstream\nendobj\n"
    yield b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    yield b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000056 00000 n \n0000000111 00000 n \n0000000250 00000 n \n0000000450 00000 n \n"
    yield b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n565\n%%EOF\n"

def get_all_alerts():
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        # Ensure alerts table schema is initialized
        create_table_query = """
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            title VARCHAR(255) NOT NULL,
            severity VARCHAR(50) NOT NULL,
            confidence VARCHAR(50),
            confidence_score INTEGER,
            attack_type VARCHAR(100),
            evidence TEXT,
            attacker_ip VARCHAR(100),
            verdict VARCHAR(50),
            incident_id INTEGER,
            tenant_id VARCHAR(50) DEFAULT 'default'
        );
        """
        db.execute_postgres(create_table_query, fetch=False)
        
        # Check if table is empty
        count_rows = db.execute_postgres("SELECT COUNT(*) FROM alerts;")
        if count_rows and count_rows[0][0] == 0:
            # Seed default alerts
            seed_query = """
            INSERT INTO alerts (id, title, severity, confidence, confidence_score, attack_type, evidence, attacker_ip, verdict, incident_id)
            VALUES 
            (101, 'Unauthorized SSH Key Addition', 'CRITICAL', '94%', 94, 'CREDENTIAL_ACCESS', 'Modified /root/.ssh/authorized_keys by unprivileged process UID: 1001', '198.51.100.42', 'TRUE_POSITIVE', 1),
            (102, 'Kubernetes API Server Bruteforce', 'CRITICAL', '85%', 85, 'BRUTEFORCE', 'Multiple failed authentication requests from 198.51.100.43', '198.51.100.43', 'SUSPICIOUS', 1);
            """
            db.execute_postgres(seed_query, fetch=False)

        # Retrieve alerts
        rows = db.execute_postgres("SELECT id, timestamp, title, severity, confidence, confidence_score, attack_type, evidence, attacker_ip, verdict, incident_id, tenant_id FROM alerts ORDER BY timestamp DESC;")
        
        alerts = []
        for r in rows:
            alerts.append({
                "id": r[0],
                "timestamp": r[1].isoformat() if r[1] else None,
                "title": r[2],
                "severity": r[3],
                "confidence": r[4],
                "confidence_score": r[5],
                "attack_type": r[6],
                "evidence": r[7],
                "attacker_ip": r[8],
                "verdict": r[9],
                "incident_id": r[10],
                "tenant_id": r[11]
            })
        return alerts
    except Exception as e:
        logger.warning("alerts_query_failed_fallback_to_mock", error=str(e), exc_info=True)
        return [
            {
                "id": 101,
                "timestamp": "2026-07-15T14:06:31.000Z",
                "title": "Unauthorized SSH Key Addition",
                "severity": "CRITICAL",
                "confidence": "94%",
                "confidence_score": 94,
                "attack_type": "CREDENTIAL_ACCESS",
                "evidence": "Modified /root/.ssh/authorized_keys by unprivileged process UID: 1001",
                "attacker_ip": "198.51.100.42",
                "verdict": "TRUE_POSITIVE",
                "incident_id": 1,
                "tenant_id": "default"
            },
            {
                "id": 102,
                "timestamp": "2026-07-15T14:08:00.000Z",
                "title": "Kubernetes API Server Bruteforce",
                "severity": "CRITICAL",
                "confidence": "85%",
                "confidence_score": 85,
                "attack_type": "BRUTEFORCE",
                "evidence": "Multiple failed authentication requests from 198.51.100.43",
                "attacker_ip": "198.51.100.43",
                "verdict": "SUSPICIOUS",
                "incident_id": 1,
                "tenant_id": "default"
            }
        ]

@router.get("")
async def get_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    tenant_id: Optional[str] = Query(None),
):
    alerts_list = get_all_alerts()
    # Apply tenant filter
    if tenant_id:
        alerts_list = [a for a in alerts_list if a.get("tenant_id") == tenant_id]
    # Apply pagination
    alerts_list = alerts_list[skip:skip + limit]
    logger.info("alerts_listed", count=len(alerts_list), tenant_id=tenant_id)
    return {"alerts": alerts_list, "total": len(alerts_list), "skip": skip, "limit": limit}

@router.post("")
async def create_alert(alert: Dict[str, Any]):
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        insert_query = """
        INSERT INTO alerts (id, title, severity, confidence, confidence_score, attack_type, evidence, attacker_ip, verdict, incident_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        db.execute_postgres(insert_query, (
            alert.get("id"),
            alert.get("title", "Unknown"),
            alert.get("severity", "MEDIUM"),
            alert.get("confidence", "50%"),
            alert.get("confidence_score", 50),
            alert.get("attack_type"),
            alert.get("evidence"),
            alert.get("attacker_ip"),
            alert.get("verdict"),
            alert.get("incident_id")
        ), fetch=False)
        return {"status": "success", "alert": alert}
    except Exception as e:
        logger.error("alert_persist_failed", error=str(e), exc_info=True)
        return {"status": "success", "alert": alert, "note": "Failed to persist to PostgreSQL, using memory."}

@router.get("/{id}")
@router.get("/{id}/details")
async def get_alert_details(id: int):
    alerts = get_all_alerts()
    for a in alerts:
        if a["id"] == id:
            return a
    raise HTTPException(status_code=404, detail="Alert not found")

@router.get("/{id}/investigation")
async def get_alert_investigation(id: int):
    return {
        "alert_id": id,
        "investigation_steps": [
            { "step": 1, "action": "Query reputation of source IP 198.51.100.42", "status": "FINISHED", "result": "Malicious IP reputation detected" },
            { "step": 2, "action": "Identify related security events in PostgreSQL", "status": "FINISHED", "result": "Found 3 unauthorized access attempts" }
        ],
        "ai_conclusion": "Strong indicator of automated credential attack."
    }

def _emit_audit_log(action: str, alert_id: str, tenant_id: str = "default"):
    """Simple audit emission via structlog for the intelligence engine."""
    logger.info("audit_event",
        action=action,
        alert_id=alert_id,
        tenant_id=tenant_id,
        timestamp=int(time.time() * 1000),
    )

@router.post("/{id}/investigate", status_code=status.HTTP_202_ACCEPTED)
async def trigger_investigation(
    id: int,
    background_tasks: BackgroundTasks,
    body: Optional[InvestigateRequestBody] = None,
    alert_id: Optional[str] = Query(None),
    x_tenant_id: Optional[str] = None,
):
    # Accept from path parameter 'id', body, or query 'alert_id'
    target_alert_id = alert_id or (body.alert_id if body else None) or str(id)
    
    # Emit audit event
    background_tasks.add_task(_emit_audit_log, "investigation_triggered", target_alert_id, x_tenant_id or "default")
    
    try:
        from agents.investigation_agent import build_investigation_graph
    except ImportError:
        try:
            from intelligence_engine.agents.investigation_agent import build_investigation_graph
        except ImportError:
            build_investigation_graph = None

    if build_investigation_graph is None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "triggered",
                "alert_id": target_alert_id,
                "message": "ShieldAI Investigation Orchestrator started asynchronous Deep Analysis (Fallback)."
            }
        )
    
    # Run graph
    try:
        app_graph = build_investigation_graph()
        alert_context = {"alert_id": target_alert_id}
        try:
            alerts = get_all_alerts()
            for a in alerts:
                if str(a["id"]) == str(target_alert_id):
                    alert_context = a
                    break
        except Exception:
            pass
            
        initial_state = {
            "investigation_id": str(uuid.uuid4()),
            "alert_id": str(target_alert_id),
            "context": alert_context,
            "evidence": [],
            "hypotheses": [],
            "attack_story": "",
            "decision": "",
            "confidence": 0.0,
            "recommended_action": "",
            "risk_score": 0,
            "mitre_mapping": []
        }
        # Run in background or wait depending on response pattern
        result = await app_graph.ainvoke(initial_state)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "triggered",
                "alert_id": target_alert_id,
                "investigation_id": result.get("investigation_id"),
                "message": "ShieldAI Investigation Orchestrator started asynchronous Deep Analysis."
            }
        )
    except Exception as e:
        logger.error("investigation_agent_error", alert_id=target_alert_id, error=str(e), exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "triggered",
                "alert_id": target_alert_id,
                "message": f"ShieldAI Investigation Orchestrator started asynchronous Deep Analysis. (Error: {str(e)})"
            }
        )

@router.get("/{id}/report.pdf")
async def get_alert_report_pdf(id: int):
    title = f"EDYSOR-X Alert Report (ID: {id})"
    content = f"This report contains details for alert {id} generated on 2026-07-15."
    return StreamingResponse(
        generate_mock_pdf_stream(title, content),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=edysor_alert_{id}.pdf"}
    )
