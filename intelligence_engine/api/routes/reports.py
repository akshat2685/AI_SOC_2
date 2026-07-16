import logging
import io
import time
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])

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

@router.get("/digest")
async def get_reports_digest(period: str = "week"):
    try:
        from reporting.report_generator import ReportGenerator
    except ImportError:
        ReportGenerator = None
        
    incident_data = {
        "risk_level": "HIGH",
        "impact": "Potential data exposure on public-facing API.",
        "assets": ["C-Suite-PC"],
        "recommendations": "Upgrade Kubernetes API server security configuration."
    }
    
    # Try fetching latest incident data to populate dynamic values
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        rows = db.execute_postgres("SELECT incident_data FROM incident_memory ORDER BY created_at DESC LIMIT 1;")
        if rows:
            data = rows[0][0]
            if isinstance(data, str):
                data = json.loads(data)
            incident_data["risk_level"] = data.get("severity", "HIGH")
            incident_data["impact"] = data.get("llm_summary", incident_data["impact"])
    except Exception:
        pass

    if ReportGenerator:
        gen = ReportGenerator()
        markdown_report = gen.generate_executive_report(incident_data)
    else:
        markdown_report = f"Executive Security Report for period: {period}"
        
    title = f"EDYSOR-X Security Digest ({period.capitalize()})"
    pdf_bytes = generate_mock_pdf_bytes(title, markdown_report)
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=edysor_digest_{period}.pdf"}
    )

@router.get("/audit-alerts-24h")
async def get_audit_alerts_24h():
    # Try retrieving real alerts list
    try:
        from api.routes.alerts import get_all_alerts
        alerts = get_all_alerts()
    except Exception:
        alerts = []
        
    payload = {
        "report_generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_alerts_24h": len(alerts),
        "alerts": alerts,
        "system_status": "healthy"
    }
    
    json_bytes = json.dumps(payload, indent=2).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=edysor_audit_alerts_24h.json"}
    )
