from fastapi import APIRouter

router = APIRouter()

@router.get("/stats")
async def get_stats():
    return {"active_incidents": 0, "open_alerts": 0, "threats_blocked": 0, "system_health": "100%"}

@router.post("/chat")
async def chat(query: dict):
    return {"response": "I am the AI Copilot. How can I help you today?"}

@router.get("/mitre/mappings")
async def get_mitre_mappings():
    return []

@router.get("/audit-log")
async def get_audit_log():
    return []

@router.get("/approvals")
async def get_approvals():
    return []

# Payments
@router.get("/payments/status")
async def get_payment_status(username: str = ""):
    return {"premium": True}

@router.post("/payments/checkout")
async def checkout(data: dict):
    return {"success": True, "message": "Upgraded successfully"}

@router.post("/payments/downgrade")
async def downgrade(data: dict):
    return {"success": True, "premium": False}

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.database import get_db
from app.domain.models import Asset

# Digital Twin
@router.get("/digital_twin/topology")
async def get_topology(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset))
    assets = result.scalars().all()
    
    nodes = []
    edges = []
    
    # Track by type to build edges
    db_servers = []
    web_servers = []
    workstations = []
    
    for a in assets:
        nodes.append({
            "id": a.hostname,
            "label": a.asset_type.split(" ")[0] if a.asset_type else "Host",
            "properties": {
                "ip": a.ip_address,
                "criticality": a.criticality.value if a.criticality else "Medium"
            }
        })
        
        # Categorize for edge creation
        atype = a.asset_type.lower() if a.asset_type else ""
        if "database" in atype or "db" in atype:
            db_servers.append(a.hostname)
        elif "web" in atype:
            web_servers.append(a.hostname)
        else:
            workstations.append(a.hostname)
            
    # Connect workstations to web servers
    edge_id = 1
    for w in workstations:
        for web in web_servers:
            edges.append({
                "id": f"e{edge_id}",
                "source": w,
                "target": web,
                "type": "CONNECTS_TO",
                "properties": {"protocol": "HTTPS"}
            })
            edge_id += 1
            
    # Connect web servers to database servers
    for web in web_servers:
        for db_srv in db_servers:
            edges.append({
                "id": f"e{edge_id}",
                "source": web,
                "target": db_srv,
                "type": "CONNECTS_TO",
                "properties": {"protocol": "TCP/5432"}
            })
            edge_id += 1

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
    
    db_servers = []
    web_servers = []
    workstations = []
    
    for a in assets:
        atype = a.asset_type.lower() if a.asset_type else ""
        if "database" in atype or "db" in atype:
            db_servers.append(a.hostname)
        elif "web" in atype:
            web_servers.append(a.hostname)
        else:
            workstations.append(a.hostname)
            
    # Simulate lateral movement based on node_id
    if node_id in workstations:
        # Compromise moves from workstation -> web server -> DB server
        for web in web_servers:
            affected_nodes.append({"id": web})
            affected_edges.append({
                "source": node_id,
                "target": web,
                "probability": risk_factor * 0.8
            })
            for db_srv in db_servers:
                affected_nodes.append({"id": db_srv})
                affected_edges.append({
                    "source": web,
                    "target": db_srv,
                    "probability": risk_factor * 0.6
                })
    elif node_id in web_servers:
        # Moves to DB servers
        for db_srv in db_servers:
            affected_nodes.append({"id": db_srv})
            affected_edges.append({
                "source": node_id,
                "target": db_srv,
                "probability": risk_factor * 0.9
            })

    # Filter out duplicates
    unique_nodes = {n["id"]: n for n in affected_nodes}.values()

    return {
        "status": "success",
        "blast_radius_score": min(risk_factor * 1.5, 0.99),
        "critical_assets_at_risk": len(db_servers),
        "affected_nodes": list(unique_nodes),
        "affected_edges": affected_edges
    }

@router.get("/digital_twin/blast-radius")
async def get_blast_radius():
    return {"nodes": [], "edges": []}

@router.get("/digital_twin/attack-paths")
async def get_attack_paths():
    return {"paths": []}

@router.delete("/digital_twin/cleanup")
async def cleanup():
    return {"status": "success"}

# Executive
@router.get("/executive/metrics")
async def executive_metrics():
    return {"metrics": []}

# Firewall
@router.get("/firewall/blocks")
async def get_firewall_blocks():
    return []

@router.post("/firewall/block")
async def block_ip(data: dict):
    return {"status": "success"}

@router.post("/firewall/unblock")
async def unblock_ip(data: dict):
    return {"status": "success"}

# Threat Intel
@router.get("/threat-intel/cve/{cve}")
async def cve_intel(cve: str):
    return {"cve": cve, "intel": "No data"}

@router.get("/threat-intel/ip/{ip}")
async def ip_intel(ip: str):
    return {"ip": ip, "intel": "No data"}

@router.post("/threat-intel/sync")
async def sync_ti():
    return {"status": "success"}

@router.post("/threat-intel/kev/sync")
async def sync_kev():
    return {"status": "success"}

# Integrations
@router.get("/integrations/status")
async def integrations_status():
    return []

@router.post("/integrations/sync")
async def sync_integrations():
    return {"status": "success"}
