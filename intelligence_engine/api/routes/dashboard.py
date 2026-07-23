import structlog
import random
from fastapi import APIRouter
from typing import Dict, Any, List

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Dashboard"])

@router.get("/stats")
@router.get("/dashboard/stats")
async def get_stats():
    incident_count = 0
    alert_count = 0
    block_count = 0
    pending_approvals = 0
    
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        # Count PostgreSQL tables
        res = db.execute_postgres("SELECT COUNT(*) FROM incident_memory;")
        incident_count = res[0][0] if res else 0
        
        res = db.execute_postgres("SELECT COUNT(*) FROM alerts;")
        alert_count = res[0][0] if res else 0
        
        res = db.execute_postgres("SELECT COUNT(*) FROM action_approvals WHERE status = 'PENDING';")
        pending_approvals = res[0][0] if res else 0
    except Exception as e:
        logger.warning(f"Postgres counts failed: {e}")
        # Default mock counts
        incident_count = 1
        alert_count = 2
        pending_approvals = 1
        
    try:
        try:
            from api.database import db
        except ImportError:
            from intelligence_engine.api.database import db
        
        # Count Redis blocks hash keys
        client = db.get_redis_client()
        block_count = client.hlen("firewall_blocks")
    except Exception as e:
        logger.warning(f"Redis blocks count failed: {e}")
        block_count = 1
        
    return {
        "incidents": incident_count,
        "alerts": alert_count,
        "firewallBlocks": block_count,
        "pendingApprovals": pending_approvals,
        "eventRate": 4.2,
        "logCount": 15420
    }

@router.get("/executive/metrics")
@router.get("/dashboard/executive/metrics")
async def get_executive_metrics():
    return {
        "riskScore": 42.5,
        "mttd": 12.8,
        "mttr": 45.4,
        "precision": 94.2,
        "totalCostPrevented": "$124,500",
        "weeklyTrends": [12, 19, 3, 5, 2, 3]
    }

@router.get("/risk-heatmap")
@router.get("/dashboard/risk-heatmap")
@router.get("/api/risk-heatmap")
async def get_risk_heatmap():
    heatmap = [
        {"region": "US-East", "risk_score": random.randint(10, 100)},
        {"region": "EU-West", "risk_score": random.randint(10, 100)},
        {"region": "AP-South", "risk_score": random.randint(10, 100)},
    ]
    return {"heatmap": heatmap}

@router.get("/mitre-matrix")
@router.get("/dashboard/mitre-matrix")
@router.get("/api/mitre-matrix")
async def get_mitre_matrix():
    return {"matrix": []}
