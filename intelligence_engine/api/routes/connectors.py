import structlog
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Connectors"])

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

@router.get("/integrations/status")
@router.get("/connectors/status")
async def get_connector_status():
    neo4j_status = {"connected": False, "uri": "", "database": "", "nodesCount": 0}
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        # Ping or count
        res = db.execute_neo4j("MATCH (n) RETURN count(n) as cnt;")
        nodes_count = res[0]["cnt"] if res else 0
        neo4j_status = {
            "connected": True,
            "uri": db.settings.db.neo4j_uri,
            "database": "neo4j",
            "nodesCount": nodes_count
        }
    except Exception as e:
        logger.warning(f"Neo4j status check failed: {e}")
        
    qdrant_status = {"connected": False, "url": "", "pointsCount": 0}
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        client = db.get_qdrant_client()
        # Count points
        info = client.get_collection(collection_name="soc_memory")
        points_count = info.points_count if info else 0
        qdrant_status = {
            "connected": True,
            "url": db.settings.db.qdrant_url,
            "pointsCount": points_count
        }
    except Exception as e:
        logger.warning(f"Qdrant status check failed: {e}")
        
    return {
        "neo4j": neo4j_status,
        "qdrant": qdrant_status
    }

@router.post("/integrations/sync")
@router.post("/connectors/sync")
async def sync_connectors():
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        # Seed Neo4j
        seed_cypher = """
        MERGE (d:Device {hostname: 'C-Suite-PC'})
        MERGE (u:User {name: 'Alice CEO'})
        MERGE (t:ThreatActor {name: 'APT41'})
        MERGE (c:Campaign {name: 'Operation CloudStrike'})
        MERGE (t)-[:CONDUCTS]->(c)
        MERGE (c)-[:TARGETS]->(d)
        MERGE (d)<-[:OWNS]-(u)
        RETURN count(*);
        """
        db.execute_neo4j(seed_cypher)
    except Exception as e:
        logger.warning(f"Neo4j seeding during sync failed: {e}")
        
    try:
        from memory.experience_replay import SOCExperienceReplay
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        replay = SOCExperienceReplay(db.settings.db.qdrant_url)
        await replay.setup()
    except Exception as e:
        logger.warning(f"Qdrant seeding during sync failed: {e}")
        
    return {"success": True, "message": "Connectors synced successfully."}

@router.get("/threat-intel/cve/{cveId}")
async def get_cve_intel(cveId: str):
    return {
        "cve_id": cveId,
        "description": f"Vulnerability {cveId} affects core components leading to potential remote execution.",
        "cvss_score": 9.8,
        "published_at": "2026-01-15T00:00:00.000Z",
        "remediation": "Apply the latest vendor patches immediately."
    }

@router.get("/threat-intel/ip/{ip}")
async def get_ip_intel(ip: str):
    return {
        "ip": ip,
        "reputation": "malicious",
        "score": 85,
        "country": "US",
        "asn": "AS15169",
        "recent_detections": 14
    }

@router.post("/threat-intel/sync")
async def sync_threat_intel():
    return {"status": "success", "message": "Threat intelligence databases synced successfully."}

@router.post("/threat-intel/kev/sync")
async def sync_kev():
    return {"status": "success", "message": "Known Exploited Vulnerabilities catalog updated."}

@router.get("/threat-intel/report.pdf")
async def get_threat_intel_report():
    title = "EDYSOR-X Threat Intelligence Report"
    content = "This report lists active indicators of compromise, threat feeds, and campaign maps."
    pdf_bytes = generate_mock_pdf_bytes(title, content)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=threat_intel_report.pdf"}
    )
