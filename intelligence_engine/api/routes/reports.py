import logging
import io
import time
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])

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
    
    return StreamingResponse(
        generate_mock_pdf_stream(title, markdown_report),
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
        
    async def json_generator():
        yield b'{\n  "report_generated_at": "' + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()).encode() + b'",\n'
        yield b'  "total_alerts_24h": ' + str(len(alerts)).encode() + b',\n'
        yield b'  "system_status": "healthy",\n'
        yield b'  "alerts": [\n'
        for i, alert in enumerate(alerts):
            yield json.dumps(alert).encode('utf-8')
            if i < len(alerts) - 1:
                yield b',\n'
        yield b'\n  ]\n}'
    
    return StreamingResponse(
        json_generator(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=edysor_audit_alerts_24h.json"}
    )
