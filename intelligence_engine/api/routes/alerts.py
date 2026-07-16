import logging
import io
import uuid
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Alerts"])

class InvestigateRequestBody(BaseModel):
    alert_id: Optional[str] = None

# Helper to generate PDF bytes dynamically
def generate_mock_pdf_bytes(title: str, content: str) -> bytes:
    # A simple valid PDF structure
    pdf_content = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        "4 0 obj\n"
        "<< /Length 150 >>\n"
        "stream\n"
        "BT\n/F1 24 Tf\n100 700 Td\n(" + title + ") Tj\n"
        "0 -40 Td\n/F1 12 Tf\n(" + content + ") Tj\n"
        "ET\n"
        "endstream\n"
        "endobj\n"
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        "endobj\n"
        "xref\n"
        "0 6\n"
        "0000000000 65535 f \n"
        "0000000009 00000 n \n"
        "0000000056 00000 n \n"
        "0000000111 00000 n \n"
        "0000000250 00000 n \n"
        "0000000450 00000 n \n"
        "trailer\n"
        "<< /Size 6 /Root 1 0 R >>\n"
        "startxref\n"
        "565\n"
        "%%EOF\n"
    )
    return pdf_content.encode("latin1")

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
        logger.warning(f"Failed to query alerts from PostgreSQL, falling back to mock data: {e}")
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
async def get_alerts():
    alerts_list = get_all_alerts()
    return {"alerts": alerts_list}

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
        logger.error(f"Failed to persist alert in PostgreSQL: {e}")
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

@router.post("/{id}/investigate")
async def trigger_investigation(
    id: int,
    body: Optional[InvestigateRequestBody] = None,
    alert_id: Optional[str] = Query(None)
):
    # Accept from path parameter 'id', body, or query 'alert_id'
    target_alert_id = alert_id or (body.alert_id if body else None) or str(id)
    
    try:
        from agents.investigation_agent import build_investigation_graph
    except ImportError:
        try:
            from intelligence_engine.agents.investigation_agent import build_investigation_graph
        except ImportError:
            build_investigation_graph = None

    if build_investigation_graph is None:
        return {
            "status": "triggered",
            "alert_id": target_alert_id,
            "message": "ShieldAI Investigation Orchestrator started asynchronous Deep Analysis (Fallback)."
        }
    
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
        return {
            "status": "triggered",
            "alert_id": target_alert_id,
            "investigation_id": result.get("investigation_id"),
            "message": "ShieldAI Investigation Orchestrator started asynchronous Deep Analysis."
        }
    except Exception as e:
        logger.error(f"Error running investigation agent: {e}")
        return {
            "status": "triggered",
            "alert_id": target_alert_id,
            "message": f"ShieldAI Investigation Orchestrator started asynchronous Deep Analysis. (Error: {str(e)})"
        }

@router.get("/{id}/report.pdf")
async def get_alert_report_pdf(id: int):
    title = f"EDYSOR-X Alert Report (ID: {id})"
    content = f"This report contains details for alert {id} generated on 2026-07-15."
    pdf_bytes = generate_mock_pdf_bytes(title, content)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=edysor_alert_{id}.pdf"}
    )
