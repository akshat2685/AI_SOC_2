import structlog
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.infrastructure.database import get_db
from app.domain.models import Asset, Alert, Incident, AuditEvent

router = APIRouter()
logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Dashboard & Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    try:
        inc_count = (await db.execute(select(func.count(Incident.id)))).scalar() or 0
        alert_count = (await db.execute(select(func.count(Alert.id)))).scalar() or 0
    except Exception:
        inc_count = 0
        alert_count = 0
    return {
        "active_incidents": inc_count,
        "open_alerts": alert_count,
        "threats_blocked": 0,
        "system_health": "healthy",
    }

@router.post("/chat")
async def chat(query: dict):
    return {"response": "I am the AI Copilot. How can I help you today?"}

# ---------------------------------------------------------------------------
# MITRE ATT&CK
# ---------------------------------------------------------------------------

@router.get("/mitre/mappings")
async def get_mitre_mappings():
    return []

# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

@router.get("/audit-log")
async def get_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(
            select(AuditEvent).order_by(desc(AuditEvent.id)).offset(skip).limit(limit)
        )
        events = result.scalars().all()
        logger.info("audit_log_listed", count=len(events))
        return events
    except Exception as e:
        logger.error("audit_log_failed", error=str(e))
        return []

# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@router.get("/approvals")
async def get_approvals():
    return []

# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@router.get("/payments/status")
async def get_payment_status():
    return {"premium": True}

@router.post("/payments/checkout")
async def checkout(data: dict):
    logger.info("checkout_requested")
    return {"success": True, "message": "Upgraded successfully"}

@router.post("/payments/downgrade")
async def downgrade(data: dict):
    logger.info("downgrade_requested")
    return {"success": True, "premium": False}

# ---------------------------------------------------------------------------
# Digital Twin - Topology
# ---------------------------------------------------------------------------

@router.get("/digital_twin/topology")
async def get_topology(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset))
    assets = result.scalars().all()

    nodes = []
    edges = []
    db_servers, web_servers, workstations = [], [], []

    for a in assets:
        nodes.append({
            "id": a.hostname,
            "label": a.asset_type.split(" ")[0] if a.asset_type else "Host",
            "properties": {
                "ip": a.ip_address,
                "criticality": a.criticality.value if a.criticality else "Medium",
            },
        })
        atype = (a.asset_type or "").lower()
        if "database" in atype or "db" in atype:
            db_servers.append(a.hostname)
        elif "web" in atype:
            web_servers.append(a.hostname)
        else:
            workstations.append(a.hostname)

    edge_id = 1
    for w in workstations:
        for web in web_servers:
            edges.append({"id": f"e{edge_id}", "source": w, "target": web, "type": "CONNECTS_TO", "properties": {"protocol": "HTTPS"}})
            edge_id += 1
    for web in web_servers:
        for db_srv in db_servers:
            edges.append({"id": f"e{edge_id}", "source": web, "target": db_srv, "type": "CONNECTS_TO", "properties": {"protocol": "TCP/5432"}})
            edge_id += 1

    logger.info("topology_fetched", node_count=len(nodes), edge_count=len(edges))
    return {"nodes": nodes, "edges": edges}

@router.post("/digital_twin/simulate")
async def simulate(data: dict, db: AsyncSession = Depends(get_db)):
    node_id = data.get("node_id", "")
    attack_type = data.get("attack_type", "RANSOMWARE")
    risk_factor = data.get("risk_factor", 0.5)

    result = await db.execute(select(Asset))
    assets = result.scalars().all()

    affected_nodes = [{"id": node_id}]
    affected_edges = []
    db_servers, web_servers, workstations = [], [], []

    for a in assets:
        atype = (a.asset_type or "").lower()
        if "database" in atype or "db" in atype:
            db_servers.append(a.hostname)
        elif "web" in atype:
            web_servers.append(a.hostname)
        else:
            workstations.append(a.hostname)

    if node_id in workstations:
        for web in web_servers:
            affected_nodes.append({"id": web})
            affected_edges.append({"source": node_id, "target": web, "probability": risk_factor * 0.8})
            for db_srv in db_servers:
                affected_nodes.append({"id": db_srv})
                affected_edges.append({"source": web, "target": db_srv, "probability": risk_factor * 0.6})
    elif node_id in web_servers:
        for db_srv in db_servers:
            affected_nodes.append({"id": db_srv})
            affected_edges.append({"source": node_id, "target": db_srv, "probability": risk_factor * 0.9})

    unique_nodes = {n["id"]: n for n in affected_nodes}.values()
    logger.info("simulation_complete", attack_type=attack_type, node_id=node_id, blast_radius=min(risk_factor * 1.5, 0.99))
    return {
        "status": "success",
        "blast_radius_score": min(risk_factor * 1.5, 0.99),
        "critical_assets_at_risk": len(db_servers),
        "affected_nodes": list(unique_nodes),
        "affected_edges": affected_edges,
    }

@router.get("/digital_twin/blast-radius")
async def get_blast_radius():
    return {"nodes": [], "edges": []}

@router.get("/digital_twin/attack-paths")
async def get_attack_paths():
    return {"paths": []}

@router.delete("/digital_twin/cleanup")
async def cleanup():
    logger.info("digital_twin_cleanup")
    return {"status": "success"}

# ---------------------------------------------------------------------------
# Executive Metrics
# ---------------------------------------------------------------------------

@router.get("/executive/metrics")
async def executive_metrics(db: AsyncSession = Depends(get_db)):
    try:
        inc_count = (await db.execute(select(func.count(Incident.id)))).scalar() or 0
        alert_count = (await db.execute(select(func.count(Alert.id)))).scalar() or 0
    except Exception:
        inc_count = 0
        alert_count = 0
    return {"metrics": {"total_incidents": inc_count, "total_alerts": alert_count}}

# ---------------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------------

@router.get("/firewall/blocks")
async def get_firewall_blocks():
    return []

@router.post("/firewall/block")
async def block_ip(data: dict):
    ip = data.get("ip", "")
    logger.info("firewall_block_ip", ip=ip)
    return {"status": "success", "ip": ip}

@router.post("/firewall/unblock")
async def unblock_ip(data: dict):
    ip = data.get("ip", "")
    logger.info("firewall_unblock_ip", ip=ip)
    return {"status": "success", "ip": ip}

# ---------------------------------------------------------------------------
# Threat Intelligence
# ---------------------------------------------------------------------------

@router.get("/threat-intel/cve/{cve}")
async def cve_intel(cve: str):
    logger.info("threat_intel_cve_lookup", cve=cve)
    return {"cve": cve, "intel": "No data"}

@router.get("/threat-intel/ip/{ip}")
async def ip_intel(ip: str):
    logger.info("threat_intel_ip_lookup", ip=ip)
    return {"ip": ip, "intel": "No data"}

@router.post("/threat-intel/sync")
async def sync_ti():
    logger.info("threat_intel_sync")
    return {"status": "success"}

@router.post("/threat-intel/kev/sync")
async def sync_kev():
    logger.info("kev_sync")
    return {"status": "success"}

# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

@router.get("/integrations/status")
async def integrations_status():
    return []

@router.post("/integrations/sync")
async def sync_integrations():
    logger.info("integrations_sync")
    return {"status": "success"}
